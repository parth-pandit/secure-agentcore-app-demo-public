# Lambda Integration Tests

Integration tests for Orders API Lambda functions against the live DynamoDB table `dev-orders-table`.

## Prerequisites

1. AWS credentials configured (via `aws configure` or environment variables)
2. Access to the `dev-orders-table` DynamoDB table in your AWS account
3. Python 3.9+ installed
4. Required dependencies installed:
   ```bash
   pip install boto3
   ```

## Running Tests

### Test Individual Functions

Run each test separately to verify specific functionality:

```bash
# Test CREATE order
python tests/integration/lambdas/test_create_order.py

# Test GET all orders
python tests/integration/lambdas/test_get_orders.py

# Test UPDATE order
python tests/integration/lambdas/test_update_order.py
```

### Test Complete Workflow

Run all tests in sequence to verify the complete API workflow:

```bash
python tests/integration/lambdas/test_all.py
```

This will:
1. Create a new order (ORD-TEST-001)
2. Retrieve all orders
3. Update the created order
4. Retrieve all orders again to verify the update

## Test Configuration

### Changing the Table Name

If you want to test against a different DynamoDB table, modify the `DYNAMODB_TABLE_NAME` environment variable in each test file:

```python
os.environ['DYNAMODB_TABLE_NAME'] = 'your-table-name'
```

### Customizing Test Data

Edit the test data in each test file:

**test_create_order.py:**
```python
event = {
    'body': json.dumps({
        'order_id': 'ORD-TEST-001',  # Change order ID
        'order_date': '2025-12-27',
        'item_name': 'Test Widget',
        'qty': 5,
        'status': 'pending'
    })
}
```

**test_update_order.py:**
```python
event = {
    'body': json.dumps({
        'order_id': 'ORD-TEST-001',  # Must match existing order
        'status': 'completed',
        'qty': 10
    })
}
```

## Expected Output

### Successful CREATE Test
```
Testing CREATE ORDER...
Request: {"order_id": "ORD-TEST-001", ...}
--------------------------------------------------
Status Code: 201
Response Body: {"message": "Order created successfully", ...}
--------------------------------------------------
✓ Order created successfully!
Order ID: ORD-TEST-001
Item: Test Widget
Quantity: 5
Status: pending
```

### Successful GET Test
```
Testing GET ORDERS...
--------------------------------------------------
Status Code: 200
--------------------------------------------------
✓ Retrieved 1 orders successfully!

Orders:

1. Order ID: ORD-TEST-001
   Date: 2025-12-27
   Item: Test Widget
   Quantity: 5
   Status: pending
```

### Successful UPDATE Test
```
Testing UPDATE ORDER...
Request: {"order_id": "ORD-TEST-001", ...}
--------------------------------------------------
Status Code: 200
Response Body: {"message": "Order updated successfully", ...}
--------------------------------------------------
✓ Order updated successfully!

Updated Order:
Order ID: ORD-TEST-001
Date: 2025-12-27
Item: Test Widget
Quantity: 10
Status: completed
```

## Troubleshooting

### Error: "Unable to locate credentials"
Configure AWS credentials:
```bash
aws configure
```

### Error: "Table not found"
Verify the table exists:
```bash
aws dynamodb describe-table --table-name dev-orders-table
```

### Error: "Order not found" (UPDATE test)
Make sure to run the CREATE test first, or update the `order_id` in the UPDATE test to match an existing order.

### Error: "Access Denied"
Ensure your AWS credentials have the following DynamoDB permissions:
- `dynamodb:GetItem`
- `dynamodb:PutItem`
- `dynamodb:UpdateItem`
- `dynamodb:Scan`

## Cleanup

After testing, you may want to delete test orders from the table:

```bash
aws dynamodb delete-item \
  --table-name dev-orders-table \
  --key '{"order_id": {"S": "ORD-TEST-001"}}'
```

## Notes

- These tests interact with the live DynamoDB table in your AWS account
- Test data will be persisted in the table unless manually deleted
- Consider using a separate test table for integration testing
- Tests require active AWS credentials with appropriate permissions
