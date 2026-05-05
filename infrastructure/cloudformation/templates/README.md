# CloudFormation Templates

This directory contains CloudFormation templates for deploying the complete application infrastructure using a parent-child nested stack architecture.

## Architecture Overview

The infrastructure is organized into **1 parent template** that orchestrates **5 child templates** (nested stacks):

```
Parent Template (parent.yaml)
├── Backend API Stack (backend-api-stack.yaml)
├── AgentCore Stack (agentcore-stack.yaml)
├── Agent App Stack (agent-app-stack.yaml)
├── Frontend Stack (frontend-stack.yaml)
└── Monitoring Stack (monitoring-stack.yaml)
```

## Template Structure

### Parent Template: `parent.yaml`

**Purpose**: Orchestrates deployment of all child stacks with proper dependencies and parameter passing.

**Key Features**:
- Defines all configuration parameters with sensible defaults
- Creates 5 nested stacks using `AWS::CloudFormation::Stack` resources
- Manages dependencies between stacks using `DependsOn` attributes
- Aggregates and exports outputs from all child stacks
- Applies consistent tagging across all resources

**Parameters**:
- Environment configuration (dev/staging/prod)
- S3 bucket names for templates and Lambda code
- Identity Provider settings (IDP URLs, client IDs, secrets)
- JWT authentication settings (JWKS URL, issuer, audience)
- Optional settings (Bedrock model, log level, CloudFront config, SNS topic)

**Outputs**:
- API Gateway URL
- AgentCore Gateway URL and Runtime ID
- Agent Proxy Lambda ARN
- OAuth Callback URL
- CloudFront domain name
- S3 bucket name
- CloudWatch dashboard name

### Child Template 1: `backend-api-stack.yaml`

**Purpose**: Deploy Orders API with Lambda functions, DynamoDB, API Gateway, and JWT authorizer.

**Resources**:
- DynamoDB table with GSIs (order_date, item_name, status)
- 4 Lambda functions (get_orders, create_order, update_order, authorizer)
- API Gateway REST API with custom JWT authorizer
- IAM roles for Lambda execution and API Gateway
- CloudWatch log group for authorizer audit logs

**Dependencies**: None (deployed first)

**Exports**:
- ApiUrl
- ApiGatewayId
- AuthorizerFunctionName
- DynamoDBTableName
- DynamoDBTableArn

### Child Template 2: `agentcore-stack.yaml`

**Purpose**: Deploy AWS Bedrock AgentCore components (Gateway, Identity, Runtime, Target).

**Resources**:
- IAM roles for Gateway and Runtime
- AgentCore Gateway with MCP protocol and JWT authorization
- OAuth2 credential provider (Microsoft OAuth2)
- Gateway Target with OpenAPI schema from S3
- AgentCore Runtime with Python 3.12 and Strands agent
- Default endpoint with PUBLIC network mode

**Dependencies**: 
- Backend API Stack (requires API URL)

**Exports**:
- GatewayId
- GatewayUrl
- GatewayRoleArn
- CredentialProviderArn
- CallbackUrl
- TargetId
- AgentRuntimeId
- AgentRuntimeArn

### Child Template 3: `agent-app-stack.yaml`

**Purpose**: Deploy AI agent application components (Proxy Lambda, OAuth Callback Lambda).

**Resources**:
- IAM roles for both Lambda functions
- Agent Proxy Lambda (invokes AgentCore Runtime)
- OAuth Callback Lambda with function URL
- Lambda permissions for invocation

**Dependencies**: 
- AgentCore Stack (requires Agent Runtime ARN)

**Exports**:
- AgentProxyFunctionArn
- AgentProxyFunctionName
- OAuthCallbackFunctionArn
- OAuthCallbackUrl

### Child Template 4: `frontend-stack.yaml`

**Purpose**: Deploy static website hosting infrastructure (S3 + CloudFront).

**Resources**:
- S3 bucket with versioning enabled
- CloudFront Origin Access Identity
- S3 bucket policy for CloudFront access
- CloudFront distribution with SPA routing support

**Dependencies**: None (can deploy in parallel)

**Exports**:
- S3BucketName
- S3BucketUrl
- CloudFrontDistributionId
- CloudFrontDomainName

### Child Template 5: `monitoring-stack.yaml`

**Purpose**: Deploy CloudWatch dashboards, alarms, and log metric filters.

**Resources**:
- CloudWatch dashboard with API and Lambda metrics
- 3 log metric filters (auth failures, errors, denials)
- 5 CloudWatch alarms (auth failures, errors, Lambda errors, unusual access, throttles)
- SNS notifications for critical alarms

**Dependencies**: 
- Backend API Stack (requires API Gateway ID and authorizer function name)

**Exports**:
- DashboardName
- AuthFailuresAlarmArn
- AuthErrorsAlarmArn
- LambdaErrorsAlarmArn
- UnusualAccessAlarmArn
- ThrottlesAlarmArn

## Stack Dependencies

The deployment order is enforced through `DependsOn` attributes:

```
1. Backend API Stack (no dependencies)
   ↓
2. AgentCore Stack (depends on: Backend API Stack)
   ↓
3. Agent App Stack (depends on: AgentCore Stack)
   ↓
4. Frontend Stack (no dependencies, deploys in parallel)
   ↓
5. Monitoring Stack (depends on: Backend API Stack)
```

## Deployment Workflow

### Prerequisites

1. **S3 Buckets**: Create two S3 buckets:
   - Templates bucket: Stores child CloudFormation templates
   - Lambda code bucket: Stores Lambda deployment packages

2. **Lambda Packages**: Package all Lambda functions using `scripts/package-lambdas.sh`

3. **Parameter Files**: Create environment-specific parameter files in `../parameters/`

### Deployment Steps

1. **Validate Templates**:
   ```bash
   ./scripts/validate-templates.sh
   ```

2. **Deploy Stack**:
   ```bash
   ./scripts/deploy-stack.sh <stack-name> <templates-bucket> <lambda-bucket>
   ```

3. **Monitor Deployment**:
   - Watch CloudFormation console for stack creation progress
   - Parent stack creates child stacks in dependency order
   - Each child stack creates its resources

4. **Verify Outputs**:
   ```bash
   aws cloudformation describe-stacks \
     --stack-name <stack-name> \
     --query 'Stacks[0].Outputs' \
     --output table \
     --no-cli-pager
   ```

### Cleanup

To delete all stacks:
```bash
./scripts/cleanup-stack.sh <stack-name>
```

**Note**: The cleanup script will:
- Empty S3 buckets before deletion (prevents deletion failures)
- Delete parent stack (cascades to all child stacks)
- Wait for complete deletion

## Parameter Management

Parameter files are stored in `../parameters/` directory:

- `dev-parameters.json` - Development environment
- `staging-parameters.json` - Staging environment
- `prod-parameters.json` - Production environment

### Required Parameters (No Defaults)

These must be provided for each environment:

- `IdpDiscoveryUrl` - Identity Provider Discovery URL
- `GatewayIdpClientId` - Gateway IDP Client ID
- `AgentIdpClientId` - Agent IDP Client ID
- `TargetIdpClientId` - Target IDP Client ID
- `TargetIdpClientSecret` - Target IDP Client Secret (use Secrets Manager in production)
- `TargetIdpTenantId` - Target IDP Tenant ID
- `JwksUrl` - JWKS URL for JWT token validation
- `TokenIssuer` - Expected JWT token issuer
- `TokenAudience` - Expected JWT token audience

### Optional Parameters (With Defaults)

- `Environment` - Environment name (default: "dev")
- `BedrockModelId` - Bedrock model ID (default: "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
- `LogLevel` - Application log level (default: "INFO")
- `CloudFrontPriceClass` - CloudFront price class (default: "PriceClass_100")
- `SslCertificateArn` - Optional SSL certificate for CloudFront
- `SnsTopicArn` - Optional SNS topic for CloudWatch alarms

## Cross-Stack References

Child stacks export outputs that are referenced by other stacks:

### Backend API Stack → AgentCore Stack
- `ApiUrl` - Used to configure AgentCore Gateway Target

### AgentCore Stack → Agent App Stack
- `AgentRuntimeArn` - Used by Agent Proxy Lambda to invoke runtime

### Backend API Stack → Monitoring Stack
- `ApiGatewayId` - Used for API Gateway metrics
- `AuthorizerFunctionName` - Used for Lambda authorizer metrics

## Resource Tagging

All resources are tagged with:

- `Environment` - Environment name (dev/staging/prod)
- `ManagedBy` - "CloudFormation"
- `Project` - Component name (OrdersAPI, AgentCore, AgentApp, Frontend, Monitoring)

Tags enable:
- Cost allocation and tracking
- Resource filtering and organization
- Compliance and governance

## Security Best Practices

### IAM Permissions

- All IAM roles follow least privilege principle
- Lambda execution roles have minimal required permissions
- AgentCore roles use service-specific trust policies

### Secrets Management

- Store sensitive parameters in AWS Secrets Manager
- Reference secrets using CloudFormation dynamic references:
  ```yaml
  TargetIdpClientSecret: !Sub '{{resolve:secretsmanager:${SecretName}:SecretString:client_secret}}'
  ```

### Encryption

- DynamoDB tables use AWS-managed encryption
- S3 buckets use server-side encryption (AES256)
- Lambda environment variables are encrypted at rest
- CloudWatch logs are encrypted

## Cost Optimization

### Development Environment
- Use `PriceClass_100` for CloudFront (lowest cost)
- Set `LogLevel` to "DEBUG" for troubleshooting
- Use minimal Lambda memory (512 MB)
- DynamoDB uses PAY_PER_REQUEST billing

### Production Environment
- Use `PriceClass_All` for CloudFront (best performance)
- Set `LogLevel` to "INFO" or "WARNING"
- Optimize Lambda memory based on profiling
- Consider DynamoDB provisioned capacity for predictable workloads

### Cost Monitoring
- Use AWS Cost Explorer with resource tags
- Set up billing alarms for unexpected costs
- Review CloudWatch logs retention policies

## Troubleshooting

### Stack Creation Failures

1. **Check CloudFormation Events**:
   ```bash
   aws cloudformation describe-stack-events \
     --stack-name <stack-name> \
     --no-cli-pager
   ```

2. **Common Issues**:
   - Missing IAM permissions for CloudFormation
   - Invalid parameter values
   - Resource naming conflicts
   - Service quotas exceeded
   - Circular dependencies between stacks

3. **Rollback Behavior**:
   - CloudFormation automatically rolls back on failure
   - Child stacks roll back independently
   - Parent stack rolls back if any child fails

### Stack Update Failures

1. **Review Change Set**:
   ```bash
   aws cloudformation describe-change-set \
     --change-set-name <change-set-name> \
     --stack-name <stack-name> \
     --no-cli-pager
   ```

2. **Common Issues**:
   - Immutable resource properties changed (requires replacement)
   - Resource dependencies prevent updates
   - Insufficient permissions for new resources

### Stack Deletion Failures

1. **Common Issues**:
   - S3 buckets not empty (use cleanup script)
   - Resources created outside CloudFormation
   - DependsOn relationships prevent deletion

2. **Manual Cleanup**:
   - Empty S3 buckets manually
   - Delete resources created outside CloudFormation
   - Retry stack deletion

## Migration from Existing Infrastructure

See `../docs/MIGRATION_GUIDE.md` for detailed migration procedures including:

- Resource import strategies
- Data migration for stateful resources
- Backward compatibility considerations
- Rollback procedures

## Additional Documentation

- `../docs/IAM_PERMISSIONS.md` - Required IAM permissions for deployment
- `../docs/COST_ESTIMATION.md` - Detailed cost analysis and optimization
- `../docs/MIGRATION_GUIDE.md` - Migration strategy and procedures

## Support

For issues or questions:
1. Review CloudFormation events and logs
2. Check AWS service quotas and limits
3. Verify IAM permissions
4. Consult AWS CloudFormation documentation: https://docs.aws.amazon.com/cloudformation/

---

**Last Updated**: 2026-05-01  
**CloudFormation Version**: AWS::CloudFormation::2010-09-09  
**Minimum AWS CLI Version**: 2.0.0
