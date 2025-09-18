terraform {
  required_version = ">= 1.6.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # TODO: Configure remote backend
  # backend "s3" {
  #   bucket         = "spotify-clone-terraform-state-dev"
  #   key            = "envs/dev/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "spotify-clone-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = "dev"
      Project     = "spotify-clone"
      ManagedBy   = "terraform"
      Owner       = var.owner
      CostCenter  = var.cost_center
    }
  }
}