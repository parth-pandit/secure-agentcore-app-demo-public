/**
 * Configuration Accessor Module
 * 
 * Provides type-safe access to configuration values with fallback support.
 * If APP_CONFIG is not available, falls back to hardcoded default values
 * to maintain backward compatibility.
 */

const ConfigAccessor = {
  /**
   * Get authentication configuration
   * @returns {Object} Auth configuration with clientId, authority, redirectUri, and scopes
   */
  getAuthConfig() {
    const config = window.APP_CONFIG?.auth;
    if (!config) {
      console.warn('Using hardcoded auth config fallback - APP_CONFIG.auth not found');
      return {
        clientId: "f8595cc5-9f3a-4459-81d7-abd0c3d67b1a",
        authority: "https://login.microsoftonline.com/d96b138a-fa21-4e19-a6cd-031770526997",
        redirectUri: "https://d31elkamfvqevy.cloudfront.net/",
        scopes: ["f8595cc5-9f3a-4459-81d7-abd0c3d67b1a/.default"]
      };
    }
    return config;
  },

  /**
   * Get API endpoint configuration
   * @returns {Object} API configuration with agentcoreEndpoint and wsSignEndpoint
   */
  getApiConfig() {
    const config = window.APP_CONFIG?.api;
    if (!config) {
      console.warn('Using hardcoded API config fallback - APP_CONFIG.api not found');
      return {
        agentcoreEndpoint: "https://oy24mor22e.execute-api.us-west-2.amazonaws.com/invoke",
        wsSignEndpoint: ""
      };
    }
    return config;
  },

  /**
   * Get runtime configuration
   * @returns {Object} Runtime configuration with maxAuthRetries and cookieExpirationMinutes
   */
  getRuntimeConfig() {
    const config = window.APP_CONFIG?.runtime;
    if (!config) {
      console.warn('Using hardcoded runtime config fallback - APP_CONFIG.runtime not found');
      return {
        maxAuthRetries: 2,
        cookieExpirationMinutes: 15
      };
    }
    return config;
  }
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ConfigAccessor;
}
