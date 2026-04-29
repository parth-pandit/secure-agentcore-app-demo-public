# Deployment Checklist

Use this checklist to track your deployment progress.

## Pre-Deployment

- [ ] AWS CLI installed and configured
- [ ] Python 3.7+ installed
- [ ] pip installed
- [ ] AWS credentials configured (`aws sts get-caller-identity` works)
- [ ] S3 bucket created or identified for Lambda code
- [ ] Project cloned/downloaded to local machine

## Deployment Steps

### Phase 1: Package Lambda Functions

- [ ] Navigate to project root directory
- [ ] Make package script executable: `chmod +x infrastructure/scripts/package-lambdas.sh`
- [ ] Run packaging script: `./infrastructure/scripts/package-lambdas.sh`
- [ ] Verify 4 zip files created in `infrastructure/lambda-packages/`:
  - [ ] `get_orders.zip`
  - [ ] `create_order.zip`
  - [ ] `update_order.zip`
  - [ ] `authorizer.zip`

### Phase 2: Deploy CloudFormation Stack

- [ ] Set environment variables:
  ```bash
  export STACK_NAME="dev-orders-api"
  export S3_BUCKET="your-bucket-name"
  export REGION="us-west-2"
  ```
- [ ] Make deploy script executable: `chmod +x infrastructure/scripts/deploy-stack.sh`
- [ ] Run deployment script with parameters
- [ ] Wait for stack creation to complete (5-10 minutes)
- [ ] Verify stack status: `aws cloudformation describe-stacks --stack-name $STACK_NAME`

### Phase 3: Verify Deployment

- [ ] Get API URL from CloudFormation outputs
- [ ] Save API URL to environment variable
- [ ] Verify DynamoDB table created
- [ ] Verify Lambda functions created:
  - [ ] get_orders
  - [ ] create_order
  - [ ] update_order
  - [ ] authorizer
- [ ] Verify API Gateway created
- [ ] Verify CloudWatch Log Groups created

### Phase 4: Generate Test Token

- [ ] Navigate to `tests/utils` directory
- [ ] Run token generator script
- [ ] Copy generated token
- [ ] Save token to environment variable: `export TOKEN="Bearer ..."`

### Phase 5: Test API Endpoints

- [ ] Test GET /orders with valid token (expect 200)
- [ ] Test POST /orders with valid token (expect 201)
- [ ] Test PUT /orders with valid token (expect 200)
- [ ] Test GET /orders without token (expect 401)
- [ ] Test GET /orders with invalid token (expect 401)
- [ ] Test GET /orders with unauthorized user (expect 403)

### Phase 6: Run Test Suite

- [ ] Install test dependencies: `pip3 install pytest hypothesis boto3 moto`
- [ ] Run unit tests: `pytest tests/unit/ -v`
- [ ] Run integration tests: `pytest tests/integration/ -v`
- [ ] Run all tests: `pytest tests/ -v`
- [ ] Verify 296 tests pass, 1 skipped

### Phase 7: Verify Logging

- [ ] Get Lambda Authorizer function name
- [ ] View CloudWatch logs: `aws logs tail /aws/lambda/<function-name> --follow`
- [ ] Verify authentication success logs
- [ ] Verify authorization attempt logs
- [ ] Verify audit logs contain user email
- [ ] Verify logs are structured JSON

### Phase 8: Set Up Monitoring (Optional)

- [ ] Get API Gateway ID
- [ ] Run dashboard creation script
- [ ] Verify dashboard created in CloudWatch console
- [ ] Create SNS topic for alarms (optional)
- [ ] Run alarms creation script (optional)
- [ ] Verify alarms created in CloudWatch console

## Post-Deployment Verification

### Functional Tests

- [ ] API responds to authenticated requests
- [ ] API rejects unauthenticated requests
- [ ] API rejects unauthorized users
- [ ] API rejects expired tokens
- [ ] API rejects invalid signatures
- [ ] All CRUD operations work correctly

### Security Tests

- [ ] Cannot access API without token
- [ ] Cannot access API with invalid token
- [ ] Cannot access API with expired token
- [ ] Cannot access API as unauthorized user
- [ ] Tokens are validated against JWKS
- [ ] Authorization policies are enforced

### Logging Tests

- [ ] Authentication attempts are logged
- [ ] Authorization decisions are logged
- [ ] User context is included in logs
- [ ] Logs are structured JSON
- [ ] Logs contain timestamps
- [ ] Sensitive data is filtered from logs

### Performance Tests

- [ ] Lambda Authorizer completes within 3 seconds
- [ ] Authorization caching works (5-minute TTL)
- [ ] API responds within acceptable time
- [ ] No Lambda throttling occurs

## Documentation Review

- [ ] Read [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- [ ] Read [AUTHENTICATION_SETUP.md](docs/AUTHENTICATION_SETUP.md)
- [ ] Read [TESTING_GUIDE.md](docs/TESTING_GUIDE.md)
- [ ] Read [MONITORING_AND_ALERTING.md](docs/MONITORING_AND_ALERTING.md)
- [ ] Read [API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md)

## Next Steps

- [ ] Configure real Azure Entra ID (see AUTHENTICATION_SETUP.md)
- [ ] Update authorized users list
- [ ] Set up production environment
- [ ] Configure CI/CD pipeline
- [ ] Set up CloudWatch alarms with SNS notifications
- [ ] Integrate with your application
- [ ] Train team on authentication flow
- [ ] Document runbook for incident response

## Troubleshooting Reference

If you encounter issues, check:

1. **Deployment fails**: Check CloudFormation events in AWS Console
2. **401 errors**: Generate fresh token, check JWKS URL
3. **403 errors**: Verify user in authorized users list
4. **Test failures**: Check Python dependencies installed
5. **No logs**: Wait 5 minutes, verify function invoked
6. **Import errors**: Install dependencies with pip3

## Cleanup (When Done Testing)

- [ ] Delete CloudFormation stack
- [ ] Delete Lambda packages from S3
- [ ] Delete CloudWatch dashboard
- [ ] Delete CloudWatch alarms
- [ ] Delete CloudWatch log groups (optional)
- [ ] Delete S3 bucket (optional)

## Success Criteria

✅ All items checked above
✅ API deployed and accessible
✅ Authentication working correctly
✅ Authorization enforced properly
✅ All tests passing
✅ Logs visible in CloudWatch
✅ Monitoring dashboard created

## Deployment Summary

**Date Deployed:** _______________

**Stack Name:** _______________

**API URL:** _______________

**Region:** _______________

**Environment:** _______________

**Deployed By:** _______________

**Notes:**
_______________________________________________
_______________________________________________
_______________________________________________

---

**Status:** 
- [ ] Deployment In Progress
- [ ] Deployment Complete
- [ ] Testing In Progress
- [ ] Testing Complete
- [ ] Production Ready

**Sign-off:** _______________  **Date:** _______________
