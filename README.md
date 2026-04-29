# Orders API with Azure Entra ID Authentication

This repository contains a production-ready Orders API with JWT-based authentication and role-based authorization, built on AWS Lambda, API Gateway, and DynamoDB, integrated directly with Azure Entra ID.

## Features

✅ **Direct Azure Entra ID Integration** - Token validation directly from Azure Entra ID  
✅ **JWT Authentication** - Signature verification using Azure public keys  
✅ **Role-Based Authorization** - Configurable user permissions per endpoint  
✅ **Comprehensive Audit Logging** - All access attempts logged to CloudWatch  
✅ **Authorization Caching** - 5-minute cache for improved performance  
✅ **Property-Based Testing** - 296 tests with Hypothesis library  
✅ **CloudWatch Monitoring** - Dashboards and alarms for security events  
✅ **Infrastructure as Code** - CloudFormation templates for deployment  

## Quick Start

Get deployed and tested in 10 minutes:

```bash
# 1. Configure Azure Entra ID
# - Register application in Azure Portal
# - Note your Tenant ID and Application ID
# - Configure API permissions (openid, email, profile)
# See docs/AUTHENTICATION_SETUP.md for detailed steps

# 2. Package Lambda functions
./infrastructure/scripts/package-lambdas.sh

# 3. Deploy to AWS with Azure Entra ID configuration
./infrastructure/scripts/deploy-stack.sh \
  dev-orders-api \
  your-s3-bucket \
  dev \
  "https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys" \
  "https://login.microsoftonline.com/<TENANT_ID>/v2.0" \
  "<APPLICATION_ID>" \
  '{"user@yourdomain.com":{"permissions":["GET","POST","PUT"],"resources":["*"]}}'

# 4. Get your API URL
export API_URL=$(aws cloudformation describe-stacks \
  --stack-name dev-orders-api \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

# 5. Test with mock token (for local testing)
cd tests/utils
export TOKEN=$(python3 -c "from token_generator import MockTokenGenerator; print('Bearer ' + MockTokenGenerator().generate_token('user@yourdomain.com'))")
cd ../..
curl -X GET "$API_URL" -H "Authorization: $TOKEN"

# 6. Test with real Azure token (for integration testing)
./tests/utils/generate_azure_token.sh
# Follow prompts to authenticate and get real Azure token
```

See [QUICK_START.md](QUICK_START.md) for detailed quick start instructions.

## Documentation

### Deployment
- **[QUICK_START.md](QUICK_START.md)** - Get deployed in 10 minutes
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete deployment instructions
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Track your deployment progress
- **[COMMAND_REFERENCE.md](COMMAND_REFERENCE.md)** - All commands in one place

### Configuration & Testing
- **[docs/AUTHENTICATION_SETUP.md](docs/AUTHENTICATION_SETUP.md)** - Configure Azure Entra ID
- **[docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)** - Test scenarios and examples
- **[docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md)** - Complete API reference

### Monitoring & Operations
- **[docs/MONITORING_AND_ALERTING.md](docs/MONITORING_AND_ALERTING.md)** - CloudWatch setup and incident response
- **[infrastructure/monitoring/README.md](infrastructure/monitoring/README.md)** - Monitoring scripts usage

## Architecture

**Authentication Flow**: Azure Entra ID → API Gateway → Lambda Authorizer → Backend Lambdas

```
┌─────────────────┐
│     Client      │
│  (Web/Mobile)   │
└────────┬────────┘
         │ 1. Request with Azure JWT Token
         │    Authorization: Bearer <token>
         ▼
┌─────────────────────────┐
│     API Gateway         │
│  (Regional Endpoint)    │
└────────┬────────────────┘
         │ 2. Invoke Authorizer
         ▼
┌─────────────────────────┐      ┌──────────────────────┐
│   Lambda Authorizer     │      │   Azure Entra ID     │
│                         │──3──▶│   JWKS Endpoint      │
│ • Fetch JWKS           │      │                      │
│ • Verify Signature     │◀─4───│   Public Keys        │
│ • Validate Claims      │      └──────────────────────┘
│ • Check Permissions    │
│ • Generate IAM Policy  │
└────────┬────────────────┘
         │ 5. Return Allow/Deny Policy
         ▼
┌─────────────────────────┐
│     API Gateway         │
│  (Policy Enforcement)   │
└────────┬────────────────┘
         │ 6. Route to Backend (if allowed)
         ▼
┌─────────────────────────┐      ┌──────────────────────┐
│   Backend Lambdas       │      │      DynamoDB        │
│                         │──7──▶│   orders-table       │
│ • get_orders           │      │                      │
│ • create_order         │◀─8───│   Query/Write Data   │
│ • update_order         │      └──────────────────────┘
└────────┬────────────────┘
         │ 9. Return Response
         ▼
┌─────────────────────────┐
│     API Gateway         │
└────────┬────────────────┘
         │ 10. Return to Client
         ▼
┌─────────────────┐
│     Client      │
└─────────────────┘

         ║
         ║ All authentication & authorization events
         ▼
┌─────────────────────────┐
│   CloudWatch Logs       │
│                         │
│ • Authentication logs   │
│ • Authorization logs    │
│ • Audit trail          │
│ • Error tracking       │
└─────────────────────────┘
```

**Key Components**:
- **Azure Entra ID**: Issues JWT tokens, provides JWKS endpoint for public keys
- **API Gateway**: Entry point, invokes authorizer before routing
- **Lambda Authorizer**: Validates tokens, enforces authorization, caches decisions
- **Backend Lambdas**: Process business logic, interact with DynamoDB
- **DynamoDB**: Stores order data
- **CloudWatch**: Logs all authentication and authorization events

## API Endpoints

All endpoints require JWT authentication via `Authorization: Bearer <token>` header.

| Method | Endpoint | Description | Required Permission |
|--------|----------|-------------|---------------------|
| GET | `/orders` | List all orders | GET |
| POST | `/orders` | Create new order | POST |
| PUT | `/orders` | Update order | PUT |

## Security Features

### Authentication (Azure Entra ID Direct Integration)
- **Direct token validation** - No intermediary services required
- **JWT signature verification** - Using Azure Entra ID public keys from JWKS endpoint
- **Token expiration checking** - With 300-second clock skew tolerance
- **Issuer validation** - Ensures token is from your Azure tenant
- **Audience validation** - Verifies token is for your application
- **Claims extraction** - Extracts user email and other claims for authorization
- **JWKS caching** - Reduces calls to Azure Entra ID

### Authorization
- **Role-based access control (RBAC)** - User-level permissions
- **Configurable permissions** - Per HTTP method (GET, POST, PUT, DELETE)
- **Resource-level access control** - Fine-grained access to specific resources
- **Explicit deny** - Fail-closed security model for unauthorized users
- **Policy caching** - 5-minute TTL for improved performance

### Audit Logging
- **All authentication attempts logged** - Success and failure
- **All authorization decisions logged** - Allow and deny with reasons
- **User context propagated** - Email and user ID passed to backend
- **Structured JSON logs** - Easy parsing and analysis
- **CloudWatch integration** - Centralized logging and monitoring
- **Searchable audit trail** - Query by user, action, or result

### Performance
- **Authorization caching** - 5-minute TTL reduces authorizer invocations
- **JWKS caching** - Reduces external calls to Azure Entra ID
- **Lambda warm starts** - Container reuse for faster responses
- **Optimized token validation** - Completes within 3 seconds

## Testing

The project includes comprehensive test coverage with support for both mock and real Azure tokens:

- **296 tests** (99.7% pass rate)
- **Unit tests** - Mock token validation for fast testing
- **Integration tests** - Real Azure Entra ID token validation
- **Property-based tests** - Using Hypothesis for edge cases
- **Mock token generator** - For local development and unit tests
- **Real token generator** - Script to obtain Azure Entra ID tokens

### Run Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only (uses mock tokens)
pytest tests/unit/ -v

# Integration tests (may require real tokens)
pytest tests/integration/ -v

# Property-based tests
pytest tests/unit/test_audit_logging_properties.py -v
```

### Generate Test Tokens

```bash
# Mock token (for unit tests)
cd tests/utils
python3 -c "from token_generator import MockTokenGenerator; print(MockTokenGenerator().generate_token('user@yourdomain.com'))"

# Real Azure token (for integration tests)
./tests/utils/generate_azure_token.sh
```

See [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) for comprehensive testing scenarios.

## Monitoring

CloudWatch monitoring includes:

### Dashboard Widgets
- API Gateway request metrics
- Lambda Authorizer invocations and errors
- Authentication success/failure trends
- Authorization allow/deny trends
- Recent failures and errors

### Alarms
- High authentication failures (>10 in 5 min)
- Authorization errors (>5 in 5 min)
- Lambda errors (>5 in 5 min)
- Unusual access patterns (>20 denials in 10 min)
- Lambda throttles (>1 in 5 min)

Set up monitoring:
```bash
python3 infrastructure/monitoring/create_dashboard.py --stack-name dev-orders-api --region us-west-2 --api-id <api-id> --authorizer-function-name <function-name>
python3 infrastructure/monitoring/create_alarms.py --stack-name dev-orders-api --region us-west-2 --authorizer-function-name <function-name>
```

## Project Structure

```
.
├── backend/
│   └── src/
│       └── lambdas/
│           ├── authorizer.py              # Lambda Authorizer
│           ├── token_validator.py         # JWT validation
│           ├── authorization_policy.py    # RBAC logic
│           ├── audit_logger.py            # Audit logging
│           ├── get_orders.py              # GET endpoint
│           ├── create_order.py            # POST endpoint
│           └── update_order.py            # PUT endpoint
├── infrastructure/
│   ├── cloudformation/
│   │   └── secure-agentcore-app-cft.yaml # CloudFormation template
│   ├── monitoring/
│   │   ├── create_dashboard.py           # Dashboard creation
│   │   └── create_alarms.py              # Alarms creation
│   └── scripts/
│       ├── package-lambdas.sh            # Package Lambda functions
│       └── deploy-stack.sh               # Deploy CloudFormation
├── tests/
│   ├── unit/                             # Unit tests
│   ├── integration/                      # Integration tests
│   └── utils/
│       └── token_generator.py            # Mock token generator
├── docs/
│   ├── AUTHENTICATION_SETUP.md           # Azure Entra ID setup
│   ├── TESTING_GUIDE.md                  # Testing scenarios
│   ├── MONITORING_AND_ALERTING.md        # Monitoring guide
│   └── API_DOCUMENTATION.md              # API reference
├── DEPLOYMENT_GUIDE.md                   # Deployment instructions
├── QUICK_START.md                        # Quick start guide
├── DEPLOYMENT_CHECKLIST.md               # Deployment checklist
└── COMMAND_REFERENCE.md                  # Command reference
```

## Requirements

### Azure Requirements
- Azure Entra ID tenant with administrative access
- Application registered in Azure Entra ID
- API permissions configured (openid, email, profile)
- Admin consent granted for permissions

### AWS Requirements
- AWS account with administrative access
- AWS CLI configured
- S3 bucket for Lambda code

### Development Requirements
- Python 3.9+ (for Lambda runtime compatibility)
- pip (Python package manager)
- bash (for deployment scripts)

## Prerequisites

```bash
# Check AWS prerequisites
aws --version          # AWS CLI v2.x
python3 --version      # Python 3.9+
pip3 --version         # pip
aws sts get-caller-identity  # AWS credentials configured

# Check Azure prerequisites (optional, for real token testing)
az --version           # Azure CLI (optional)
```

## Azure Entra ID Setup

Before deploying, you need to configure Azure Entra ID:

1. **Register Application**
   - Go to Azure Portal → Microsoft Entra ID → App registrations
   - Click "New registration"
   - Note the Application (client) ID and Directory (tenant) ID

2. **Configure API Permissions**
   - Go to API permissions
   - Add Microsoft Graph permissions: openid, email, profile
   - Grant admin consent

3. **Configure Token Claims**
   - Go to Token configuration
   - Add optional claims: email, upn, preferred_username

4. **Get Configuration Values**
   ```bash
   TENANT_ID="your-tenant-id"
   APPLICATION_ID="your-application-id"
   JWKS_URL="https://login.microsoftonline.com/${TENANT_ID}/discovery/v2.0/keys"
   ISSUER_URL="https://login.microsoftonline.com/${TENANT_ID}/v2.0"
   ```

See [docs/AUTHENTICATION_SETUP.md](docs/AUTHENTICATION_SETUP.md) for detailed setup instructions.

## Cleanup

Remove all deployed resources:

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name dev-orders-api

# Wait for stack deletion
aws cloudformation wait stack-delete-complete --stack-name dev-orders-api

# Delete Lambda packages from S3
aws s3 rm s3://your-bucket/lambda-code/ --recursive

# Delete monitoring resources (if created)
aws cloudwatch delete-dashboards --dashboard-names dev-orders-api-auth-monitoring

# Delete CloudWatch alarms (if created)
aws cloudwatch delete-alarms --alarm-names \
  dev-orders-api-high-auth-failures \
  dev-orders-api-authorization-errors \
  dev-orders-api-lambda-errors
```

**Note**: Azure Entra ID application registration is not automatically deleted. You can keep it for future use or manually delete it from Azure Portal.

## Support

For issues or questions:

### Documentation
- **[QUICK_START.md](QUICK_START.md)** - Quick deployment guide
- **[docs/AUTHENTICATION_SETUP.md](docs/AUTHENTICATION_SETUP.md)** - Azure Entra ID configuration
- **[docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md)** - Testing with real and mock tokens
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete deployment instructions

### Troubleshooting
- Check CloudWatch Logs: `/aws/lambda/<authorizer-function-name>`
- Review API Gateway execution logs
- Verify Azure Entra ID configuration (JWKS URL, issuer, audience)
- Check CloudFormation events in AWS Console
- See [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) troubleshooting section

### Common Issues
1. **401 Unauthorized**: Check token expiration, issuer, and audience
2. **403 Forbidden**: Verify user is in AUTHORIZED_USERS configuration
3. **Token validation fails**: Ensure JWKS URL is accessible from Lambda
4. **Slow responses**: Check authorization caching is enabled (5-minute TTL)

## License

This project is provided as-is for demonstration purposes.

## Contributing

This is a demonstration project. For production use, consider:

### Security Enhancements
- **Token revocation** - Implement token blacklist or check revocation status
- **Rate limiting** - Add API Gateway usage plans and throttling
- **Secrets management** - Use AWS Secrets Manager for sensitive configuration
- **Key rotation** - Implement automatic JWKS key rotation handling
- **MFA enforcement** - Require multi-factor authentication in Azure Entra ID

### Operational Improvements
- **CI/CD pipeline** - Automate testing and deployment
- **API versioning** - Support multiple API versions
- **Request/response validation** - Add JSON schema validation
- **Error handling** - Implement comprehensive error responses
- **Monitoring dashboards** - Create custom CloudWatch dashboards
- **Alerting** - Set up SNS notifications for critical events

### Performance Optimization
- **Lambda provisioned concurrency** - Reduce cold starts
- **DynamoDB on-demand scaling** - Optimize for traffic patterns
- **API Gateway caching** - Cache GET responses
- **CloudFront distribution** - Add CDN for global distribution

### Compliance & Governance
- **Data encryption** - Enable encryption at rest and in transit
- **Backup strategy** - Implement automated backups
- **Disaster recovery** - Multi-region deployment
- **Compliance logging** - Enhanced audit trails for compliance requirements
