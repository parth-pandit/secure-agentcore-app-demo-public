#!/bin/bash
# Deploy UI to S3 and CloudFront

set -e

UI_BUCKET="${UI_BUCKET:-YOUR_UI_BUCKET_NAME}"
CLOUDFRONT_DIST_ID="${CLOUDFRONT_DIST_ID:-YOUR_CLOUDFRONT_DISTRIBUTION_ID}"

echo "🚀 Deploying UI..."

# Build configuration
echo "📦 Building configuration..."
# Navigate to frontend directory (one level up from utils)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
npm install
node build-config.js

# Validate that config.generated.js was created
if [ ! -f "src/config.generated.js" ]; then
  echo "❌ Configuration build failed: config.generated.js not found"
  exit 1
fi

echo "✅ Configuration built successfully"

cd src

# Sync to S3
echo "📤 Syncing to S3..."
aws s3 sync . s3://$UI_BUCKET/ \
  --exclude "*.md" \
  --exclude ".DS_Store"

# Invalidate CloudFront cache
echo "🔄 Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
  --distribution-id $CLOUDFRONT_DIST_ID \
  --paths "/*"

echo "✅ UI deployed successfully"
echo "🌐 URL: https://YOUR_CLOUDFRONT_DOMAIN.cloudfront.net"
