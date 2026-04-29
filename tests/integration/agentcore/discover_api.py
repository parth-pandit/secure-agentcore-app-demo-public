#!/usr/bin/env python3
"""
AgentCore Gateway API Discovery Script
Helps determine the correct API structure and requirements.
"""

import requests
import json
import sys
import os

def test_endpoint(url, method='GET', headers=None, data=None):
    """Test an endpoint and return response info."""
    try:
        if headers is None:
            headers = {}
        
        response = requests.request(method, url, headers=headers, json=data, timeout=10)
        return {
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'content': response.text[:500] if response.text else None
        }
    except Exception as e:
        return {'error': str(e)}

def main():
    gateway_url = os.environ.get('AGENTCORE_GATEWAY_URL')
    if not gateway_url:
        print("❌ AGENTCORE_GATEWAY_URL environment variable is required")
        sys.exit(1)
    
    print(f"🔍 Discovering AgentCore Gateway API structure")
    print(f"Gateway URL: {gateway_url}")
    print("=" * 60)
    
    # Test various endpoints
    endpoints_to_test = [
        ('Base MCP endpoint', f"{gateway_url}"),
        ('Health check', f"{gateway_url}/health"),
        ('OpenAPI spec', f"{gateway_url}/openapi.json"),
        ('OpenAPI spec alt', f"{gateway_url}/mcp/openapi.json"),
        ('Orders direct', f"{gateway_url}/orders"),
        ('Orders with mcp prefix', f"{gateway_url}/mcp/orders"),
        ('Orders API v1', f"{gateway_url}/api/v1/orders"),
        ('Orders MCP API v1', f"{gateway_url}/mcp/api/v1/orders"),
    ]
    
    # Test different HTTP methods
    methods_to_test = ['GET', 'POST', 'OPTIONS']
    
    # Test different headers
    headers_sets = [
        {},
        {'Content-Type': 'application/json'},
        {'X-AgentCore-Target': 'orders-api'},
        {'Content-Type': 'application/json', 'X-AgentCore-Target': 'orders-api'},
        {'Authorization': 'Bearer test-token'},
        {'Authorization': 'Bearer test-token', 'Content-Type': 'application/json', 'X-AgentCore-Target': 'orders-api'},
    ]
    
    results = []
    
    print("🧪 Testing endpoints...")
    for name, url in endpoints_to_test:
        print(f"\n📍 {name}: {url}")
        
        for method in methods_to_test:
            for i, headers in enumerate(headers_sets):
                if method == 'GET' and i > 3:  # Skip auth headers for GET discovery
                    continue
                    
                result = test_endpoint(url, method, headers)
                
                if 'error' not in result:
                    status = result['status_code']
                    if status not in [404, 405]:  # Interesting responses
                        header_desc = f"headers_{i}" if headers else "no_headers"
                        print(f"  ✅ {method} {header_desc}: {status}")
                        if result.get('content'):
                            print(f"     Content preview: {result['content'][:100]}...")
                        results.append({
                            'name': name,
                            'url': url,
                            'method': method,
                            'headers': headers,
                            'response': result
                        })
    
    print("\n" + "=" * 60)
    print("📊 Summary of successful responses:")
    
    if results:
        for result in results:
            status = result['response']['status_code']
            print(f"✅ {result['name']} ({result['method']}): {status}")
            print(f"   URL: {result['url']}")
            if result['headers']:
                print(f"   Headers: {result['headers']}")
            print()
    else:
        print("❌ No successful responses found")
        print("\n💡 Suggestions:")
        print("1. Verify the AGENTCORE_GATEWAY_URL is correct")
        print("2. Check if the gateway requires specific authentication")
        print("3. Verify the gateway is properly configured")
        print("4. Check AWS CloudWatch logs for the gateway")
    
    # Test direct API for comparison
    print("🔗 Testing direct API for comparison...")
    try:
        api_url = "https://2u8i08vno4.execute-api.us-west-2.amazonaws.com/dev/orders"
        direct_result = test_endpoint(api_url)
        print(f"Direct API status: {direct_result.get('status_code', 'error')}")
    except Exception as e:
        print(f"Direct API test failed: {e}")

if __name__ == '__main__':
    main()
