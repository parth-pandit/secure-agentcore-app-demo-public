# Orders API Lambda Functions

Python Lambda functions for managing orders in DynamoDB table `dev-orders-table`.

## API Endpoints

### 1. GET - Retrieve All Orders
**File:** `get_orders.py`
- Retrieves all order records from the DynamoDB table
- Handles pagination automatically for large datasets
- Returns order count and complete order details

**Response Example:**
```json
{
  "message": "Orders retrieved successfully",
  "count": 10,
  "orders": [...]
}
```

### 2. POST - Create New Order
**File:** `create_order.py`
- Creates a new order record in DynamoDB
- Validates all required fields before creation
- Returns the created order details

**Request Body:**
```json
{
  "order_id": "ORD-12345",
  "order_date": "2025-12-27",
  "item_name": "Product Name",
  "qty": 5,
  "status": "pending"
}
```

### 3. PUT - Update Order
**File:** `update_order.py`
- Updates existing order details by order_id
- Supports partial updates (only provided fields are updated)
- Returns updated order details

**Request Body:**
```json
{
  "order_id": "ORD-12345",
  "status": "completed",
  "qty": 10
}
```

## Deployment

### Prerequisites
- AWS CLI configured with appropriate credentials
- IAM role with DynamoDB access permissions

### Lambda Configuration
Each Lambda function requires:
- **Runtime:** Python 3.9 or higher
- **Handler:** `<filename>.lambda_handler`
- **Timeout:** 30 seconds (recommended)
- **Memory:** 256 MB (recommended)
- **Environment Variable:** 
  - `DYNAMODB_TABLE_NAME` = `dev-orders-table` (or your table name)

### IAM Permissions Required
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Scan",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/dev-orders-table"
    }
  ]
}
```

## Local Testing
Install dependencies:
```bash
pip install -r requirements.txt
```

## Notes
- All functions include CORS headers for cross-origin requests
- Error handling and logging included
- Decimal conversion handled for DynamoDB number types
