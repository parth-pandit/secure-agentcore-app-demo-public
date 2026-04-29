# Configuration Reference

Complete reference for all configuration parameters in the frontend application.

## Configuration Structure

```json
{
  "auth": { ... },
  "api": { ... },
  "runtime": { ... }
}
```

---

## Authentication Configuration (`auth`)

Configuration for Microsoft Authentication Library (MSAL) and Azure AD integration.

### `auth.clientId`

**Type**: String (UUID format)  
**Required**: Yes  
**Format**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (8-4-4-4-12 hexadecimal)  
**Environment Variable**: `MSAL_CLIENT_ID`

Azure AD application (client) ID. This uniquely identifies your application in Azure AD.

**How to get**:
1. Go to Azure Portal > Azure Active Directory > App Registrations
2. Select your application
3. Copy the "Application (client) ID" from the Overview page

**Example**:
```json
"clientId": "12345678-1234-1234-1234-123456789abc"
```

**Validation**:
- Must be a valid UUID format
- Must match the pattern: `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`

---

### `auth.authority`

**Type**: String (HTTPS URL)  
**Required**: Yes  
**Format**: `https://login.microsoftonline.com/{tenant-id}`  
**Environment Variable**: `MSAL_AUTHORITY`

Azure AD authority URL including your tenant ID. This tells MSAL which Azure AD tenant to authenticate against.

**How to get**:
1. Go to Azure Portal > Azure Active Directory > Overview
2. Copy the "Tenant ID"
3. Construct the URL: `https://login.microsoftonline.com/{tenant-id}`

**Example**:
```json
"authority": "https://login.microsoftonline.com/your-tenant-id-here"
```

**Validation**:
- Must start with `https://`
- Typically uses `login.microsoftonline.com` domain

**Alternative formats**:
- Workforce tenant: `https://login.microsoftonline.com/{tenant-id}`
- External tenant: `https://{subdomain}.ciamlogin.com/`

---

### `auth.redirectUri`

**Type**: String (HTTP/HTTPS URL)  
**Required**: Yes  
**Format**: `https://your-domain.com/` or `http://localhost:3000/` (for local dev)  
**Environment Variable**: `REDIRECT_URI`

OAuth redirect URI where Azure AD sends the authentication response. This URI must be registered in your Azure AD app registration.

**How to configure**:
1. Go to Azure Portal > Azure Active Directory > App Registrations
2. Select your application
3. Go to Authentication > Platform configurations
4. Add this URI to the "Redirect URIs" list
5. Save changes

**Example**:
```json
"redirectUri": "https://your-app-domain.cloudfront.net/"
```

**Validation**:
- Must start with `http://` or `https://`
- Must exactly match a URI registered in Azure AD
- For production, should use `https://`
- For local development, can use `http://localhost:PORT/`

**Common values**:
- Production: `https://app.example.com/`
- Staging: `https://staging.example.com/`
- Local dev: `http://localhost:3000/`

---

### `auth.scopes`

**Type**: Array of strings  
**Required**: Yes  
**Minimum items**: 1  
**Environment Variable**: Typically constructed from `MSAL_CLIENT_ID`

OAuth scopes to request during authentication. Scopes define what permissions the application requests from the user.

**Example**:
```json
"scopes": ["12345678-1234-1234-1234-123456789abc/.default"]
```

**Common patterns**:
- Default scope: `{client-id}/.default` - Requests all permissions configured in Azure AD
- Specific scopes: `["User.Read", "Mail.Send"]` - Requests specific Microsoft Graph permissions
- Custom API scopes: `["api://{client-id}/access_as_user"]` - For custom APIs

**Validation**:
- Must be an array with at least one scope
- Each scope must be a non-empty string

**Notes**:
- MSAL automatically adds OIDC scopes (openid, profile, email)
- The `.default` scope requests all permissions granted to the app in Azure AD

---

## API Configuration (`api`)

Configuration for backend API endpoints.

### `api.agentcoreEndpoint`

**Type**: String (HTTPS URL)  
**Required**: Yes  
**Format**: `https://your-api.execute-api.region.amazonaws.com/invoke`  
**Environment Variable**: `AGENTCORE_ENDPOINT`

AgentCore REST API endpoint URL. This is the primary backend API that the frontend communicates with.

**Example**:
```json
"agentcoreEndpoint": "https://abc123xyz.execute-api.us-west-2.amazonaws.com/invoke"
```

**Validation**:
- Must start with `https://`
- Should be a valid, accessible URL

**Common patterns**:
- AWS API Gateway: `https://{api-id}.execute-api.{region}.amazonaws.com/{stage}`
- Custom domain: `https://api.example.com/v1/invoke`

---

### `api.wsSignEndpoint`

**Type**: String (HTTPS URL or empty string)  
**Required**: No (optional)  
**Format**: `https://your-ws-signer.execute-api.region.amazonaws.com/sign`  
**Environment Variable**: `WS_SIGN_ENDPOINT`  
**Default**: `""` (empty string)

WebSocket signing endpoint URL. Used for WebSocket connections if available. If not provided or empty, the application falls back to HTTP-only communication.

**Example**:
```json
"wsSignEndpoint": "https://xyz789def.execute-api.us-west-2.amazonaws.com/sign"
```

**Validation**:
- Can be an empty string
- If provided, should be a valid URL (no strict HTTPS requirement for flexibility)

**Notes**:
- Optional feature - application works without WebSocket support
- Leave empty if WebSocket functionality is not needed
- When provided, enables real-time streaming responses

---

## Runtime Configuration (`runtime`)

Application runtime behavior settings.

### `runtime.maxAuthRetries`

**Type**: Integer  
**Required**: No (has default)  
**Range**: 0-10  
**Default**: 2  
**Environment Variable**: Not typically set via environment (use literal value in config.json)

Maximum number of authentication retry attempts when authorization is required.

**Example**:
```json
"maxAuthRetries": 2
```

**Validation**:
- Must be an integer
- Must be between 0 and 10 (inclusive)

**Behavior**:
- `0`: No retries, fail immediately if auth is required
- `1-10`: Retry up to N times before giving up
- Higher values give users more chances but may delay error feedback

**Recommended values**:
- Production: `2-3` (balance between user experience and performance)
- Development: `1` (fail fast for debugging)

---

### `runtime.cookieExpirationMinutes`

**Type**: Integer  
**Required**: No (has default)  
**Range**: 1-1440 (1 minute to 24 hours)  
**Default**: 15  
**Environment Variable**: Not typically set via environment (use literal value in config.json)

Cookie expiration time in minutes for runtime session cookies.

**Example**:
```json
"cookieExpirationMinutes": 15
```

**Validation**:
- Must be an integer
- Must be between 1 and 1440 (inclusive)
- 1440 minutes = 24 hours (maximum)

**Behavior**:
- Cookies are automatically refreshed when session ID changes
- Shorter values provide better security but may require more frequent re-authentication
- Longer values provide better user experience but keep session data longer

**Recommended values**:
- High security: `5-15` minutes
- Balanced: `15-30` minutes
- User convenience: `60-120` minutes
- Maximum: `1440` minutes (24 hours)

**Security considerations**:
- Shorter expiration times reduce the window for session hijacking
- Balance security needs with user experience
- Consider your application's security requirements

---

## Environment Variable Substitution

Configuration values can use environment variable placeholders:

**Syntax**: `${VARIABLE_NAME}`

**Example**:
```json
{
  "auth": {
    "clientId": "${MSAL_CLIENT_ID}",
    "authority": "${MSAL_AUTHORITY}"
  }
}
```

**Build process**:
1. Reads `config.json`
2. Replaces `${VAR_NAME}` with `process.env.VAR_NAME`
3. Fails if required variable is undefined
4. Generates `config.generated.js` with resolved values

**Best practices**:
- Use environment variables for sensitive values (client IDs, endpoints)
- Use literal values for non-sensitive settings (retry counts, timeouts)
- Document all required environment variables in `.env.example`

---

## Validation Rules

All configuration is validated against `config.schema.json` during the build process.

**Validation checks**:
- Required fields are present
- Values match expected types (string, integer, array)
- Strings match format patterns (UUID, URL)
- Numbers are within valid ranges
- Arrays have minimum required items

**Validation failure**:
- Build process exits with error code 1
- Error messages show which fields failed and why
- Deployment is prevented until configuration is valid

---

## Complete Example

```json
{
  "auth": {
    "clientId": "12345678-1234-1234-1234-123456789abc",
    "authority": "https://login.microsoftonline.com/your-tenant-id-here",
    "redirectUri": "https://your-app-domain.cloudfront.net/",
    "scopes": ["12345678-1234-1234-1234-123456789abc/.default"]
  },
  "api": {
    "agentcoreEndpoint": "https://abc123xyz.execute-api.us-west-2.amazonaws.com/invoke",
    "wsSignEndpoint": ""
  },
  "runtime": {
    "maxAuthRetries": 2,
    "cookieExpirationMinutes": 15
  }
}
```

---

## See Also

- `README.md` - Quick start guide and overview
- `MIGRATION_GUIDE.md` - Migration instructions
- `config.schema.json` - JSON schema with validation rules
- `.env.example` - Environment variable template
