#!/usr/bin/env bash
# =============================================================================
# NoemaForge GitHub Environments Setup Script
# =============================================================================
# Purpose: Create 4 deployment environments via GitHub REST API
# Usage: GITHUB_TOKEN=ghp_xxx bash .github/scripts/setup-environments.sh
# Requirements: curl, jq, GITHUB_TOKEN environment variable
# =============================================================================

set -euo pipefail

# Configuration
GITHUB_OWNER="Sinev-Maksim"
GITHUB_REPO="NoemaForge"
GITHUB_API_URL="https://api.github.com"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verify prerequisites
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo -e "${RED}❌ Error: GITHUB_TOKEN environment variable not set${NC}"
    echo "Usage: GITHUB_TOKEN=ghp_xxx bash .github/scripts/setup-environments.sh"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    echo -e "${RED}❌ Error: curl is not installed${NC}"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${RED}❌ Error: jq is not installed${NC}"
    exit 1
fi

# Function to create environment
create_environment() {
    local env_name=$1

    echo -e "${BLUE}→ Creating environment: ${env_name}${NC}"
    
    response=$(curl -s -X PUT \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "${GITHUB_API_URL}/repos/${GITHUB_OWNER}/${GITHUB_REPO}/environments/${env_name}" \
        -d '{
            "deployment_branch_policy": {
                "protected_branches": false,
                "custom_branch_policies": true
            }
        }')
    
    if echo "$response" | jq -e '.name' &>/dev/null; then
        echo -e "${GREEN}  ✓ Environment '${env_name}' created successfully${NC}"
        return 0
    else
        echo -e "${RED}  ✗ Failed to create environment '${env_name}'${NC}"
        echo "  Response: $(echo "$response" | jq -r '.message // .error // .')"
        return 1
    fi
}

# Function to add deployment branch policy
add_deployment_branch_policy() {
    local env_name=$1
    local branch_pattern=$2
    
    echo -e "${BLUE}  → Adding branch pattern: ${branch_pattern}${NC}"
    
    response=$(curl -s -X POST \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "${GITHUB_API_URL}/repos/${GITHUB_OWNER}/${GITHUB_REPO}/environments/${env_name}/deployment-branch-policies" \
        -d "{\"name\": \"${branch_pattern}\"}")
    
    if echo "$response" | jq -e '.node_id' &>/dev/null; then
        echo -e "${GREEN}    ✓ Branch pattern added${NC}"
        return 0
    else
        echo -e "${YELLOW}    ⚠ Warning: Could not add branch pattern (may require manual setup)${NC}"
        return 0
    fi
}

# Main setup
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}NoemaForge GitHub Environments Setup${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Environment 1: Development
echo -e "${BLUE}[1/4]${NC} Development Environment"
create_environment "development"  # Local dev, testing, version hotfixes
add_deployment_branch_policy "development" "develop"
add_deployment_branch_policy "development" "feature/*"
echo ""

# Environment 2: Staging
echo -e "${BLUE}[2/4]${NC} Staging Environment"
create_environment "staging"  # Pre-release validation, integration tests
add_deployment_branch_policy "staging" "staging"
add_deployment_branch_policy "staging" "release/*"
echo ""

# Environment 3: Production
echo -e "${BLUE}[3/4]${NC} Production Environment"
create_environment "production"  # Release candidate, main branch deploys
add_deployment_branch_policy "production" "main"
add_deployment_branch_policy "production" "v0.32.*"
echo ""

# Environment 4: Hotfix
echo -e "${BLUE}[4/4]${NC} Hotfix Environment"
create_environment "hotfix"  # Emergency patches only
add_deployment_branch_policy "hotfix" "hotfix/*"
add_deployment_branch_policy "hotfix" "release/hotfix/*"
echo ""

# Summary
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Environment Creation Complete!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "📋 Next steps (MANUAL - Required in GitHub UI):"
echo ""
echo "1️⃣  Add Reviewers:"
echo "   • Go to Settings → Environments"
echo "   • For each environment, add required reviewers:"
echo "     - development: code-writer"
echo "     - staging: code-writer, qa-admin"
echo "     - production: qa-admin (REQUIRED)"
echo "     - hotfix: qa-admin (REQUIRED)"
echo ""
echo "2️⃣  Add Secrets:"
echo "   • development: NOEMAFORGE_DEV_ROOT"
echo "   • staging: NOEMAFORGE_STAGING_ROOT, STAGING_MODEL_CACHE"
echo "   • production: NOEMAFORGE_PROD_ROOT, PROD_CHECKSUMS, GPG_SIGN_KEY"
echo "   • hotfix: EMERGENCY_DEPLOY_TOKEN"
echo ""
echo "3️⃣  Verify in UI:"
echo "   • https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/settings/environments"
echo ""
echo "📖 For detailed instructions, see: .github/ENVIRONMENT_SETUP.md"
echo ""
