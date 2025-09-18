locals {
  name_prefix = "spotify-clone-dev"
  
  common_tags = {
    Environment = "dev"
    Project     = "spotify-clone"
    Owner       = var.owner
    CostCenter  = var.cost_center
  }
}

# VPC Module
module "vpc" {
  source = "../../modules/vpc"

  name_prefix = local.name_prefix
  vpc_cidr    = var.vpc_cidr
  az_count    = var.az_count
  tags        = local.common_tags
}

# TODO: Add additional modules
# module "rds" {
#   source = "../../modules/rds"
#   ...
# }

# module "redis" {
#   source = "../../modules/redis"
#   ...
# }

# module "ecs" {
#   source = "../../modules/ecs"
#   ...
# }

# module "alb" {
#   source = "../../modules/alb"
#   ...
# }