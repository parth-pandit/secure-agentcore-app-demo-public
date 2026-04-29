# UI Deployment (Phase 2)

This is a static UI meant for quick testing without user authentication.

## 1) Set the Agent endpoint
Edit `ui/config.js` to point to your public endpoint.

## 2) S3 + CloudFront (recommended)

Create a private S3 bucket and use CloudFront with OAC for public hosting.

Example flow:
```
aws s3 mb s3://<your-bucket-name>
aws s3 sync ui/ s3://<your-bucket-name>
```

Then create a CloudFront distribution pointing at the bucket, and set the
CloudFront domain in your DNS (optional).

## 3) CORS
Ensure your public endpoint allows the CloudFront origin to call it.
