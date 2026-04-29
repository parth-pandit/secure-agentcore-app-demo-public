# Frontend Configuration System

This directory contains the configuration system for the frontend application. The system uses a centralized JSON configuration file with environment variable substitution at build time.

## Quick Start

### 1. Set up environment variables

Copy the example environment file and fill in your values:

```bash
cp .env.example .env.local
```

Edit `.env.local` with your actual configuration values. **Never commit this file to version control.**

### 2. Install dependencies

```bash
npm install
```

### 3. Build configuration

```bash
npm run build-config
```

This will:
- Read `config.json`
- Substitute environment variables (${VAR_NAME})
- Validate against `config.schema.json`
- Generate `src/config.generated.js`

### 4. Deploy

The deployment script automatically builds configuration:

```bash
cd ../ai-agent/src/utils
./deploy-ui.sh
```

## Configuration Files

### `config.json`
The main configuration file with environment variable placeholders:

```json
{
  "auth": {
    "clientId": "${MSAL_CLIENT_ID}",
    "authority": "${MSAL_AUTHORITY}",
    "redirectUri": "${REDIRECT_URI}",
    "scopes": ["${MSAL_CLIENT_ID}/.default"]
  },
  "api": {
    "agentcoreEndpoint": "${AGENTCORE_ENDPOINT}",
    "wsSignEndpoint": "${WS_SIGN_ENDPOINT}"
  },
  "runtime": {
    "maxAuthRetries": 2,
    "cookieExpirationMinutes": 15
  }
}
```

### `config.schema.json`
JSON schema that validates configuration structure and formats.

### `.env.example`
Template showing all required environment variables with descriptions.

### `.env.local` (gitignored)
Your local environment variables. Create this file from `.env.example`.

## How It Works

1. **Build Time**: The `build-config.js` script processes `config.json`:
   - Reads the configuration file
   - Substitutes `${VAR_NAME}` with values from `process.env.VAR_NAME`
   - Validates against the JSON schema
   - Generates `src/config.generated.js`

2. **Runtime**: The application loads configuration:
   - `index.html` loads `config.generated.js` first
   - This sets `window.APP_CONFIG` with all configuration values
   - `configAccessor.js` provides type-safe access with fallbacks
   - Application code uses `ConfigAccessor.getAuthConfig()`, etc.

## Configuration Sections

### Authentication (`auth`)
- `clientId`: Azure AD application (client) ID (UUID format)
- `authority`: Azure AD authority URL with tenant ID
- `redirectUri`: OAuth redirect URI (must be registered in Azure AD)
- `scopes`: Array of OAuth scopes to request

### API Endpoints (`api`)
- `agentcoreEndpoint`: AgentCore REST API endpoint (required)
- `wsSignEndpoint`: WebSocket signing endpoint (optional)

### Runtime Settings (`runtime`)
- `maxAuthRetries`: Maximum authentication retry attempts (0-10, default: 2)
- `cookieExpirationMinutes`: Cookie expiration time in minutes (1-1440, default: 15)

## Environment-Specific Configuration

For different environments (dev, staging, production), use different environment variable values:

**Development (.env.local)**:
```bash
MSAL_CLIENT_ID=dev-client-id
REDIRECT_URI=http://localhost:3000/
AGENTCORE_ENDPOINT=https://dev-api.example.com/invoke
```

**Production (CI/CD environment variables)**:
```bash
MSAL_CLIENT_ID=prod-client-id
REDIRECT_URI=https://app.example.com/
AGENTCORE_ENDPOINT=https://api.example.com/invoke
```

## Troubleshooting

### Build fails with "Environment variable X is not defined"
- Check that all required variables are set in `.env.local` or your environment
- Verify variable names match exactly (case-sensitive)
- Source your environment file: `source .env.local` (if using bash)

### Configuration validation fails
- Check that values match the expected formats (URLs, UUIDs, etc.)
- Review error messages for specific validation failures
- Refer to `config.schema.json` for format requirements

### Application uses hardcoded values
- Verify `config.generated.js` exists in `src/`
- Check browser console for warnings about missing APP_CONFIG
- Ensure `config.generated.js` is loaded before other scripts in `index.html`

### Deployment fails
- Run `npm run build-config` manually to see detailed errors
- Check that all environment variables are set in your deployment environment
- Verify `config.generated.js` is created successfully

## Security Best Practices

1. **Never commit sensitive values**: Use environment variables for all sensitive data
2. **Keep .env.local gitignored**: This file should never be in version control
3. **Rotate credentials regularly**: Update client IDs and secrets periodically
4. **Use different values per environment**: Dev, staging, and production should have separate credentials
5. **Validate in CI/CD**: Ensure your deployment pipeline has all required environment variables

## Backward Compatibility

The configuration system maintains backward compatibility through fallback values in `configAccessor.js`. If `APP_CONFIG` is not available, the application falls back to hardcoded default values and logs a warning.

This allows for gradual migration and ensures the application continues to work during the transition period.

## For More Information

- See `CONFIG_REFERENCE.md` for detailed parameter documentation
- See `MIGRATION_GUIDE.md` for migration instructions
- See `config.schema.json` for validation rules
