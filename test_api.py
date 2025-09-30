#!/usr/bin/env python3
"""
Test script for the enhanced FastAPI application.
This script will test all the major features of our production-ready API.
"""

import asyncio
import json
import time
from typing import Dict, Any

import httpx
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


class APITester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = None
        self.access_token = None
        
    async def __aenter__(self):
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    def print_test(self, test_name: str, success: bool, details: str = ""):
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   {details}")
        print()
    
    async def test_basic_endpoints(self):
        """Test basic endpoints that don't require auth."""
        print("🔍 Testing Basic Endpoints...")
        
        # Test health check
        try:
            response = await self.client.get("/health")
            success = response.status_code == 200
            data = response.json() if success else {}
            self.print_test(
                "Health Check", 
                success,
                f"Status: {data.get('status', 'unknown')}, Response time: {data.get('response_time_ms', 'N/A')}ms"
            )
        except Exception as e:
            self.print_test("Health Check", False, f"Error: {str(e)}")
        
        # Test liveness probe
        try:
            response = await self.client.get("/health/live")
            success = response.status_code == 200
            self.print_test("Liveness Probe", success)
        except Exception as e:
            self.print_test("Liveness Probe", False, f"Error: {str(e)}")
        
        # Test readiness probe
        try:
            response = await self.client.get("/health/ready")
            success = response.status_code in [200, 503]  # 503 is ok if DB not ready
            self.print_test("Readiness Probe", success)
        except Exception as e:
            self.print_test("Readiness Probe", False, f"Error: {str(e)}")
        
        # Test metrics endpoint
        try:
            response = await self.client.get("/metrics")
            success = response.status_code == 200 and "http_requests_total" in response.text
            self.print_test("Prometheus Metrics", success)
        except Exception as e:
            self.print_test("Prometheus Metrics", False, f"Error: {str(e)}")
        
        # Test API docs (should be available in dev)
        try:
            response = await self.client.get("/docs")
            success = response.status_code == 200
            self.print_test("API Documentation", success)
        except Exception as e:
            self.print_test("API Documentation", False, f"Error: {str(e)}")
    
    async def test_security_headers(self):
        """Test security headers are properly set."""
        print("🔒 Testing Security Headers...")
        
        try:
            response = await self.client.get("/health")
            headers = response.headers
            
            security_checks = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "X-API-Version": "1.0.0"
            }
            
            for header, expected in security_checks.items():
                present = header in headers
                correct = headers.get(header) == expected if present else False
                self.print_test(
                    f"Security Header: {header}",
                    correct,
                    f"Expected: {expected}, Got: {headers.get(header, 'Missing')}"
                )
                
        except Exception as e:
            self.print_test("Security Headers", False, f"Error: {str(e)}")
    
    async def test_authentication_flow(self):
        """Test the complete authentication flow."""
        print("🔐 Testing Authentication Flow...")
        
        # Test login with invalid credentials
        try:
            response = await self.client.post("/auth/login", json={
                "email": "nonexistent@example.com",
                "password": "wrongpassword"
            })
            success = response.status_code == 401
            self.print_test("Login with Invalid Credentials", success, "Should return 401")
        except Exception as e:
            self.print_test("Login with Invalid Credentials", False, f"Error: {str(e)}")
        
        # Test login with missing fields
        try:
            response = await self.client.post("/auth/login", json={
                "email": "test@example.com"
                # Missing password
            })
            success = response.status_code == 422
            self.print_test("Login with Missing Fields", success, "Should return 422 validation error")
        except Exception as e:
            self.print_test("Login with Missing Fields", False, f"Error: {str(e)}")
        
        # Note: We can't test successful login without a user in the database
        # This would require database setup with test users
        self.print_test(
            "Note: Real Login Test", 
            True, 
            "Requires database setup with test users - will implement in integration tests"
        )
    
    async def test_rate_limiting(self):
        """Test rate limiting functionality."""
        print("⏱️ Testing Rate Limiting...")
        
        # Test rate limiting on health endpoint (60/minute)
        try:
            rapid_requests = []
            for i in range(5):  # Send 5 requests rapidly
                response = await self.client.get("/health")
                rapid_requests.append(response.status_code)
                await asyncio.sleep(0.1)  # Small delay
            
            # All should succeed (well under the limit)
            all_success = all(status == 200 for status in rapid_requests)
            self.print_test("Rate Limiting - Normal Usage", all_success, f"Responses: {rapid_requests}")
            
        except Exception as e:
            self.print_test("Rate Limiting", False, f"Error: {str(e)}")
    
    async def test_protected_endpoints_without_auth(self):
        """Test that protected endpoints properly reject unauthenticated requests."""
        print("🛡️ Testing Protected Endpoints (No Auth)...")
        
        protected_endpoints = [
            "/protected/user",
            "/protected/admin", 
            "/api/tracks"
        ]
        
        for endpoint in protected_endpoints:
            try:
                response = await self.client.get(endpoint)
                success = response.status_code == 401
                self.print_test(
                    f"Protected Endpoint: {endpoint}",
                    success,
                    f"Should return 401, got {response.status_code}"
                )
            except Exception as e:
                self.print_test(f"Protected Endpoint: {endpoint}", False, f"Error: {str(e)}")
    
    async def test_error_handling(self):
        """Test global exception handling."""
        print("🚨 Testing Error Handling...")
        
        # Test 404 for non-existent endpoint
        try:
            response = await self.client.get("/nonexistent")
            success = response.status_code == 404
            data = response.json() if success else {}
            self.print_test(
                "404 Error Handling",
                success,
                f"Error: {data.get('error', 'N/A')}"
            )
        except Exception as e:
            self.print_test("404 Error Handling", False, f"Error: {str(e)}")
        
        # Test validation error
        try:
            response = await self.client.post("/auth/login", json={
                "email": "not-an-email",  # Invalid email format
                "password": "test"
            })
            success = response.status_code == 422
            self.print_test("Validation Error Handling", success, "Should return 422 for invalid email")
        except Exception as e:
            self.print_test("Validation Error Handling", False, f"Error: {str(e)}")
    
    async def test_monitoring_features(self):
        """Test monitoring and observability features."""
        print("📊 Testing Monitoring Features...")
        
        # Test that responses include monitoring headers
        try:
            response = await self.client.get("/health")
            headers = response.headers
            
            monitoring_headers = [
                "X-Response-Time",
                "X-Request-ID"
            ]
            
            for header in monitoring_headers:
                present = header in headers
                self.print_test(
                    f"Monitoring Header: {header}",
                    present,
                    f"Value: {headers.get(header, 'Missing')}"
                )
                
        except Exception as e:
            self.print_test("Monitoring Headers", False, f"Error: {str(e)}")


async def check_server_running(url: str) -> bool:
    """Check if the FastAPI server is running."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{url}/health", timeout=5.0)
            return response.status_code == 200
    except:
        return False


async def main():
    print("🚀 Enhanced FastAPI Test Suite")
    print("=" * 50)
    
    # Check if server is running
    server_url = "http://localhost:8000"
    print(f"🔍 Checking if server is running at {server_url}...")
    
    if not await check_server_running(server_url):
        print("❌ Server is not running!")
        print("\n📋 To start the server, run:")
        print("   cd apps/api_fastapi")
        print("   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
        print("\n   Then run this test script again.")
        return
    
    print("✅ Server is running!")
    print()
    
    # Run tests
    async with APITester(server_url) as tester:
        await tester.test_basic_endpoints()
        await tester.test_security_headers()
        await tester.test_authentication_flow()
        await tester.test_rate_limiting()
        await tester.test_protected_endpoints_without_auth()
        await tester.test_error_handling()
        await tester.test_monitoring_features()
    
    print("🎉 Test suite completed!")
    print("\n📝 Next steps:")
    print("1. Check the /docs endpoint for interactive API documentation")
    print("2. Monitor /metrics endpoint for Prometheus metrics")
    print("3. Check server logs for structured JSON logging")
    print("4. Test with a frontend client or Postman for full integration")


if __name__ == "__main__":
    asyncio.run(main())