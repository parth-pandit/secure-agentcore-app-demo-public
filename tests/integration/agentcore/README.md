# AgentCore Gateway Integration Tests

This directory contains integration tests for the AgentCore Gateway integration with the Orders API.

## Setup

1. **Set Environment Variables**:
   ```bash
   export AGENTCORE_GATEWAY_URL="https://your-agentcore-gateway.us-west-2.amazonaws.com"
   export AWS_REGION="us-west-2"
   ```

2. **Install Dependencies**:
   ```bash
   pip install requests boto3
   ```

3. **Deploy Orders API Stack** (if not already deployed):
   ```bash
   ./infrastructure/scripts/deploy-stack.sh dev-orders-api your-s3-bucket dev
   ```

## Running Tests

### All AgentCore Tests
```bash
python -m pytest tests/integration/agentcore/ -v
```

### Specific Test Classes
```bash
# Gateway integration tests
python -m pytest tests/integration/agentcore/test_agentcore_gateway.py::AgentCoreGatewayTest -v

# OpenAPI integration tests  
python -m pytest tests/integration/agentcore/test_agentcore_gateway.py::AgentCoreOpenAPITest -v
```

### Individual Tests
```bash
# Test basic connectivity
python -m pytest tests/integration/agentcore/test_agentcore_gateway.py::AgentCoreGatewayTest::test_agentcore_gateway_connectivity -v

# Test CRUD operations
python -m pytest tests/integration/agentcore/test_agentcore_gateway.py::AgentCoreGatewayTest::test_get_orders_via_agentcore -v
python -m pytest tests/integration/agentcore/test_agentcore_gateway.py::AgentCoreGatewayTest::test_create_order_via_agentcore -v
python -m pytest tests/integration/agentcore/test_agentcore_gateway.py::AgentCoreGatewayTest::test_update_order_via_agentcore -v
```

## Test Coverage

### Gateway Integration (`AgentCoreGatewayTest`)
- ✅ Basic connectivity to AgentCore Gateway
- ✅ GET /orders through gateway
- ✅ POST /orders through gateway  
- ✅ PUT /orders through gateway
- ✅ Authentication flows (valid/invalid tokens)
- ✅ Consistency between gateway and direct API calls
- ✅ Error handling and malformed requests
- ✅ Routing headers validation
- ✅ Performance characteristics and overhead

### OpenAPI Integration (`AgentCoreOpenAPITest`)
- ✅ OpenAPI 3.0 specification availability
- ✅ Schema validation for API responses
- ✅ Orders API paths in OpenAPI spec

## Configuration

The tests automatically discover your deployed Orders API stack in us-west-2. If you have multiple stacks, it will use the first one containing "orders" in the name.

### Manual Configuration
If auto-discovery fails, set these environment variables:
```bash
export API_URL="https://your-api-gateway.execute-api.us-west-2.amazonaws.com/dev/orders"
export STACK_NAME="your-orders-api-stack"
```

## Expected Results

### Successful Test Run
```
test_agentcore_gateway_connectivity ... ok
test_get_orders_via_agentcore ... ok  
test_create_order_via_agentcore ... ok
test_update_order_via_agentcore ... ok
test_authentication_via_agentcore ... ok
test_agentcore_vs_direct_api_consistency ... ok
test_agentcore_error_handling ... ok
test_agentcore_routing_headers ... ok
test_agentcore_performance ... ok
test_openapi_spec_availability ... ok
test_openapi_schema_validation ... ok
```

### Common Issues

1. **AgentCore Gateway not accessible**: Set correct `AGENTCORE_GATEWAY_URL`
2. **Orders API not found**: Deploy the stack first or set `API_URL` manually
3. **Authentication failures**: Check that mock tokens are working with your authorizer
4. **Performance test failures**: Network latency may cause timeouts

## Troubleshooting

### Debug Mode
Run with verbose output:
```bash
python -m pytest tests/integration/agentcore/ -v -s
```

### Check Resources
Verify your AWS resources:
```bash
aws cloudformation list-stacks --region us-west-2 --query 'StackSummaries[?contains(StackName, `orders`)]'
```

### Test Individual Components
Test direct API first:
```bash
python -m pytest tests/integration/test_api_with_authentication.py -v
```
