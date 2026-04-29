# Orders API Documentation

## Overview

The Orders API provides RESTful endpoints for managing orders in the system. All endpoints require authentication via Azure Entra ID JWT tokens.

**Base URL**: `https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>`

**Authentication**: Bearer token in Authorization header

**API Version**: 1.0

## Authentication

All API requests must include a valid JWT token obtained from Azure Entra ID.

### Request Header

```
Authorization: Bearer <access_token>
```

### Example

```bash
curl -X GET https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders \
  -H "Authorization: Bearer eyJraWQiOiJ..."
```

See [Authentication Setup Guide](./AUTHENTICATION_SETUP.md) for details on obtaining access tokens.

## Authorization

Access to API endpoints is controlled by user-based permissions configured in the Lambda Authorizer.

### Permission Model

- **User**: Identified by email address from JWT token
- **Permissions**: HTTP methods (GET, POST, PUT, DELETE)
- **Resources**: API resource paths (e.g., `/orders`, `/orders/*`)

### Current Configuration

Users configured in the `AuthorizedUsers` parameter have permissions based on their configuration. Example:

```json
{
  "user@yourdomain.com": {
    "permissions": ["GET", "POST", "PUT"],
    "resources": ["*"]
  }
}
```

This user has:
- **GET**: Read orders
- **POST**: Create orders
- **PUT**: Update orders
- **Resources**: All (`*`)

## Endpoints

### 1. Get Orders

Retrieve all orders or a specific order from the database.

**Endpoint**: `GET /orders`

**Authentication**: Required

**Authorization**: User must have GET permission

#### Request

**Query Parameters**:
- `order_id` (optional): Specific order ID to retrieve

**Headers**:
```
Authorization: Bearer <access_token>
```

#### Response

**Success (200 OK)**:

Get all orders:
```json
{
  "orders": [
    {
      "order_id": "order-123",
      "item_name": "Widget",
      "qty": 5,
      "status": "pending"
    },
    {
      "order_id": "order-456",
      "item_name": "Gadget",
      "qty": 3,
      "status": "completed"
    }
  ]
}
```

Get specific order:
```json
{
  "order": {
    "order_id": "order-123",
    "item_name": "Widget",
    "qty": 5,
    "status": "pending"
  }
}
```

**Error Responses**:

401 Unauthorized:
```json
{
  "message": "Unauthorized"
}
```

403 Forbidden:
```json
{
  "message": "User is not authorized to access this resource with an explicit deny"
}
```

404 Not Found (specific order):
```json
{
  "error": "Order not found"
}
```

500 Internal Server Error:
```json
{
  "error": "Internal server error"
}
```

#### Example

Get all orders:
```bash
curl -X GET "https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders" \
  -H "Authorization: Bearer eyJraWQiOiJ..."
```

Get specific order:
```bash
curl -X GET "https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders?order_id=order-123" \
  -H "Authorization: Bearer eyJraWQiOiJ..."
```

---

### 2. Create Order

Create a new order in the database.

**Endpoint**: `POST /orders`

**Authentication**: Required

**Authorization**: User must have POST permission

#### Request

**Headers**:
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Body**:
```json
{
  "order_id": "order-123",
  "item_name": "Widget",
  "qty": 5,
  "status": "pending"
}
```

**Field Descriptions**:
- `order_id` (string, required): Unique identifier for the order
- `item_name` (string, required): Name of the item being ordered
- `qty` (number, required): Quantity of items (must be positive)
- `status` (string, required): Order status (e.g., "pending", "processing", "completed", "cancelled")

#### Response

**Success (201 Created)**:
```json
{
  "message": "Order created successfully",
  "order": {
    "order_id": "order-123",
    "item_name": "Widget",
    "qty": 5,
    "status": "pending"
  }
}
```

**Error Responses**:

400 Bad Request (missing fields):
```json
{
  "error": "Missing required fields: order_id, item_name, qty, status"
}
```

401 Unauthorized:
```json
{
  "message": "Unauthorized"
}
```

403 Forbidden:
```json
{
  "message": "User is not authorized to access this resource with an explicit deny"
}
```

409 Conflict (order already exists):
```json
{
  "error": "Order already exists"
}
```

500 Internal Server Error:
```json
{
  "error": "Internal server error"
}
```

#### Example

```bash
curl -X POST "https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders" \
  -H "Authorization: Bearer eyJraWQiOiJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "order-123",
    "item_name": "Widget",
    "qty": 5,
    "status": "pending"
  }'
```

---

### 3. Update Order

Update an existing order in the database.

**Endpoint**: `PUT /orders`

**Authentication**: Required

**Authorization**: User must have PUT permission

#### Request

**Headers**:
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Body**:
```json
{
  "order_id": "order-123",
  "item_name": "Updated Widget",
  "qty": 10,
  "status": "completed"
}
```

**Field Descriptions**:
- `order_id` (string, required): Unique identifier for the order to update
- `item_name` (string, optional): Updated item name
- `qty` (number, optional): Updated quantity
- `status` (string, optional): Updated status

**Note**: Only `order_id` is required. Include only the fields you want to update.

#### Response

**Success (200 OK)**:
```json
{
  "message": "Order updated successfully",
  "order": {
    "order_id": "order-123",
    "item_name": "Updated Widget",
    "qty": 10,
    "status": "completed"
  }
}
```

**Error Responses**:

400 Bad Request (missing order_id):
```json
{
  "error": "Missing required field: order_id"
}
```

401 Unauthorized:
```json
{
  "message": "Unauthorized"
}
```

403 Forbidden:
```json
{
  "message": "User is not authorized to access this resource with an explicit deny"
}
```

404 Not Found:
```json
{
  "error": "Order not found"
}
```

500 Internal Server Error:
```json
{
  "error": "Internal server error"
}
```

#### Example

Update order status:
```bash
curl -X PUT "https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders" \
  -H "Authorization: Bearer eyJraWQiOiJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "order-123",
    "status": "completed"
  }'
```

Update multiple fields:
```bash
curl -X PUT "https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>/orders" \
  -H "Authorization: Bearer eyJraWQiOiJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "order-123",
    "item_name": "Premium Widget",
    "qty": 15,
    "status": "processing"
  }'
```

---

## Error Handling

### HTTP Status Codes

- **200 OK**: Request succeeded
- **201 Created**: Resource created successfully
- **400 Bad Request**: Invalid request parameters or body
- **401 Unauthorized**: Missing or invalid authentication token
- **403 Forbidden**: Valid token but insufficient permissions
- **404 Not Found**: Requested resource doesn't exist
- **409 Conflict**: Resource already exists
- **500 Internal Server Error**: Server-side error

### Error Response Format

All error responses follow this format:

```json
{
  "error": "Error message describing what went wrong"
}
```

Or for authentication/authorization errors:

```json
{
  "message": "Unauthorized" 
}
```

## Rate Limiting

Currently, there are no explicit rate limits on the API. However, AWS API Gateway has default throttling limits:

- **Steady-state requests**: 10,000 requests per second
- **Burst**: 5,000 requests

If you exceed these limits, you'll receive a `429 Too Many Requests` response.

## Audit Logging

All API requests are logged for security and compliance purposes.

### Logged Information

- Timestamp of request
- User email from JWT token
- HTTP method and resource path
- Source IP address
- Authorization result (Allow/Deny)
- Error details (if applicable)

### Log Location

Audit logs are stored in CloudWatch Logs:
- **Log Group**: `/aws/lambda/orders-api-authorizer`
- **Retention**: 30 days

### Log Entry Example

```json
{
  "timestamp": "2025-01-05T12:00:00.000Z",
  "event_type": "AUTHORIZATION_SUCCESS",
  "service": "orders-api-authorizer",
  "user": {
    "email": "user@yourdomain.com"
  },
  "request": {
    "method": "GET",
    "resource": "/orders",
    "source_ip": "203.0.113.1"
  },
  "result": "ALLOW"
}
```

## Security Considerations

### Token Security

- Tokens are valid for a limited time (typically 1 hour)
- Tokens should be transmitted only over HTTPS
- Never log or expose tokens in client-side code
- Implement token refresh logic in your application

### Authorization Caching

- Authorization decisions are cached for 5 minutes
- Changes to user permissions may take up to 5 minutes to take effect
- Revoked tokens may remain valid for up to 5 minutes

### Data Validation

- All input data is validated before processing
- SQL injection and XSS attacks are prevented
- Input size limits are enforced

### HTTPS Only

- All API requests must use HTTPS
- HTTP requests are not supported

## Best Practices

### 1. Token Management

```javascript
// Good: Store token securely
const token = await getTokenFromSecureStorage();

// Bad: Hardcode token
const token = "eyJraWQiOiJ..."; // Never do this!
```

### 2. Error Handling

```javascript
try {
  const response = await fetch(apiUrl, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  
  if (!response.ok) {
    if (response.status === 401) {
      // Token expired or invalid - refresh token
      await refreshToken();
    } else if (response.status === 403) {
      // Insufficient permissions - show error to user
      showPermissionError();
    }
  }
  
  return await response.json();
} catch (error) {
  // Handle network errors
  console.error('API request failed:', error);
}
```

### 3. Request Retries

```javascript
async function apiRequestWithRetry(url, options, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch(url, options);
      if (response.ok) return await response.json();
      
      // Don't retry on 4xx errors (except 429)
      if (response.status >= 400 && response.status < 500 && response.status !== 429) {
        throw new Error(`Request failed: ${response.status}`);
      }
      
      // Wait before retrying
      await new Promise(resolve => setTimeout(resolve, 1000 * Math.pow(2, i)));
    } catch (error) {
      if (i === maxRetries - 1) throw error;
    }
  }
}
```

### 4. Batch Operations

For multiple operations, consider batching requests to reduce overhead:

```javascript
// Instead of multiple individual requests
const orders = await Promise.all([
  getOrder('order-1'),
  getOrder('order-2'),
  getOrder('order-3')
]);

// Consider implementing a batch endpoint in the future
```

## SDK Examples

### JavaScript/Node.js

```javascript
const axios = require('axios');

const API_BASE_URL = 'https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>';

class OrdersAPIClient {
  constructor(accessToken) {
    this.accessToken = accessToken;
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      }
    });
  }

  async getOrders(orderId = null) {
    const params = orderId ? { order_id: orderId } : {};
    const response = await this.client.get('/orders', { params });
    return response.data;
  }

  async createOrder(order) {
    const response = await this.client.post('/orders', order);
    return response.data;
  }

  async updateOrder(orderId, updates) {
    const response = await this.client.put('/orders', {
      order_id: orderId,
      ...updates
    });
    return response.data;
  }
}

// Usage
const client = new OrdersAPIClient('your-access-token');
const orders = await client.getOrders();
```

### Python

```python
import requests

API_BASE_URL = 'https://<YOUR-API-ID>.execute-api.<YOUR-REGION>.amazonaws.com/<YOUR-STAGE>'

class OrdersAPIClient:
    def __init__(self, access_token):
        self.access_token = access_token
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
    
    def get_orders(self, order_id=None):
        params = {'order_id': order_id} if order_id else {}
        response = requests.get(
            f'{API_BASE_URL}/orders',
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def create_order(self, order):
        response = requests.post(
            f'{API_BASE_URL}/orders',
            headers=self.headers,
            json=order
        )
        response.raise_for_status()
        return response.json()
    
    def update_order(self, order_id, updates):
        data = {'order_id': order_id, **updates}
        response = requests.put(
            f'{API_BASE_URL}/orders',
            headers=self.headers,
            json=data
        )
        response.raise_for_status()
        return response.json()

# Usage
client = OrdersAPIClient('your-access-token')
orders = client.get_orders()
```

## Changelog

### Version 1.0 (Current)

- Initial release with authentication and authorization
- Three endpoints: GET, POST, PUT for orders
- Azure Entra ID integration
- Audit logging to CloudWatch
- Authorization caching (5 minutes)

## Support

For API issues or questions:
- Check [Authentication Setup Guide](./AUTHENTICATION_SETUP.md)
- Review CloudWatch Logs for detailed error information
- Contact your system administrator

## Related Documentation

- [Authentication Setup Guide](./AUTHENTICATION_SETUP.md) - How to configure Azure Entra ID and obtain tokens
- [Testing Guide](./TESTING_GUIDE.md) - Comprehensive testing scenarios
- [Deployment Guide](../DEPLOYMENT_GUIDE.md) - How to deploy the infrastructure
