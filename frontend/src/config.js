// Get API configuration from ConfigAccessor
const apiConfig = ConfigAccessor.getApiConfig();

// Update this after deploying the AgentCore proxy.
window.AGENTCORE_ENDPOINT = apiConfig.agentcoreEndpoint;
window.WS_SIGN_ENDPOINT = apiConfig.wsSignEndpoint;
