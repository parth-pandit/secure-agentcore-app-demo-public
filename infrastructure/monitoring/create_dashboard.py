#!/usr/bin/env python3
"""
Create CloudWatch Dashboard for API Authentication and Authorization Monitoring.

This script creates a CloudWatch dashboard that displays key metrics for:
- Authorization attempts (success/failure)
- Authentication failures
- Authorization denials
- Authorizer errors
- API Gateway metrics

Requirements: 4.5, 4.6
"""

import json
import boto3
import sys
from typing import Dict, Any


def create_dashboard_body(
    stack_name: str,
    region: str,
    api_id: str,
    authorizer_function_name: str
) -> Dict[str, Any]:
    """
    Create the dashboard body with all widgets.
    
    Args:
        stack_name: CloudFormation stack name
        region: AWS region
        api_id: API Gateway REST API ID
        authorizer_function_name: Lambda Authorizer function name
        
    Returns:
        Dashboard body as dictionary
    """
    dashboard_body = {
        "widgets": [
            # Row 1: Overview metrics
            {
                "type": "metric",
                "x": 0,
                "y": 0,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/ApiGateway", "Count", {"stat": "Sum", "label": "Total API Requests"}],
                        [".", "4XXError", {"stat": "Sum", "label": "4XX Errors"}],
                        [".", "5XXError", {"stat": "Sum", "label": "5XX Errors"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "API Gateway - Request Overview",
                    "period": 300,
                    "yAxis": {
                        "left": {
                            "label": "Count"
                        }
                    }
                }
            },
            {
                "type": "metric",
                "x": 8,
                "y": 0,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/Lambda", "Invocations", {"stat": "Sum", "label": "Authorizer Invocations"}, {"dimensions": {"FunctionName": authorizer_function_name}}],
                        [".", "Errors", {"stat": "Sum", "label": "Authorizer Errors"}, {"dimensions": {"FunctionName": authorizer_function_name}}],
                        [".", "Throttles", {"stat": "Sum", "label": "Authorizer Throttles"}, {"dimensions": {"FunctionName": authorizer_function_name}}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Lambda Authorizer - Invocations",
                    "period": 300,
                    "yAxis": {
                        "left": {
                            "label": "Count"
                        }
                    }
                }
            },
            {
                "type": "metric",
                "x": 16,
                "y": 0,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/Lambda", "Duration", {"stat": "Average", "label": "Avg Duration"}, {"dimensions": {"FunctionName": authorizer_function_name}}],
                        ["...", {"stat": "Maximum", "label": "Max Duration"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": region,
                    "title": "Lambda Authorizer - Duration",
                    "period": 300,
                    "yAxis": {
                        "left": {
                            "label": "Milliseconds"
                        }
                    }
                }
            },
            
            # Row 2: Authentication and Authorization metrics from logs
            {
                "type": "log",
                "x": 0,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                    "query": f"""SOURCE '/aws/lambda/{authorizer_function_name}'
| fields @timestamp, @message
| filter @message like /AUTHENTICATION_SUCCESS/
| stats count() as AuthenticationSuccesses by bin(5m)""",
                    "region": region,
                    "title": "Authentication Successes (5min intervals)",
                    "stacked": False,
                    "view": "timeSeries"
                }
            },
            {
                "type": "log",
                "x": 12,
                "y": 6,
                "width": 12,
                "height": 6,
                "properties": {
                    "query": f"""SOURCE '/aws/lambda/{authorizer_function_name}'
| fields @timestamp, @message
| filter @message like /AUTHENTICATION_FAILURE/
| stats count() as AuthenticationFailures by bin(5m)""",
                    "region": region,
                    "title": "Authentication Failures (5min intervals)",
                    "stacked": False,
                    "view": "timeSeries"
                }
            },
            
            # Row 3: Authorization decisions
            {
                "type": "log",
                "x": 0,
                "y": 12,
                "width": 12,
                "height": 6,
                "properties": {
                    "query": f"""SOURCE '/aws/lambda/{authorizer_function_name}'
| fields @timestamp, @message
| filter @message like /AUTHORIZATION_ATTEMPT/ and @message like /ALLOW/
| stats count() as AuthorizationAllowed by bin(5m)""",
                    "region": region,
                    "title": "Authorization Allowed (5min intervals)",
                    "stacked": False,
                    "view": "timeSeries"
                }
            },
            {
                "type": "log",
                "x": 12,
                "y": 12,
                "width": 12,
                "height": 6,
                "properties": {
                    "query": f"""SOURCE '/aws/lambda/{authorizer_function_name}'
| fields @timestamp, @message
| filter @message like /AUTHORIZATION_ATTEMPT/ and @message like /DENY/
| stats count() as AuthorizationDenied by bin(5m)""",
                    "region": region,
                    "title": "Authorization Denied (5min intervals)",
                    "stacked": False,
                    "view": "timeSeries"
                }
            },
            
            # Row 4: Recent authentication failures
            {
                "type": "log",
                "x": 0,
                "y": 18,
                "width": 24,
                "height": 6,
                "properties": {
                    "query": f"""SOURCE '/aws/lambda/{authorizer_function_name}'
| fields @timestamp, @message
| filter @message like /AUTHENTICATION_FAILURE/
| sort @timestamp desc
| limit 20""",
                    "region": region,
                    "title": "Recent Authentication Failures",
                    "stacked": False,
                    "view": "table"
                }
            },
            
            # Row 5: Recent authorization denials
            {
                "type": "log",
                "x": 0,
                "y": 24,
                "width": 24,
                "height": 6,
                "properties": {
                    "query": f"""SOURCE '/aws/lambda/{authorizer_function_name}'
| fields @timestamp, @message
| filter @message like /AUTHORIZATION_ATTEMPT/ and @message like /DENY/
| sort @timestamp desc
| limit 20""",
                    "region": region,
                    "title": "Recent Authorization Denials",
                    "stacked": False,
                    "view": "table"
                }
            },
            
            # Row 6: Error analysis
            {
                "type": "log",
                "x": 0,
                "y": 30,
                "width": 24,
                "height": 6,
                "properties": {
                    "query": f"""SOURCE '/aws/lambda/{authorizer_function_name}'
| fields @timestamp, @message
| filter @message like /ERROR/ or @message like /AUTHORIZATION_ERROR/
| sort @timestamp desc
| limit 20""",
                    "region": region,
                    "title": "Recent Errors",
                    "stacked": False,
                    "view": "table"
                }
            }
        ]
    }
    
    return dashboard_body


def create_dashboard(
    dashboard_name: str,
    stack_name: str,
    region: str,
    api_id: str,
    authorizer_function_name: str
) -> None:
    """
    Create or update CloudWatch dashboard.
    
    Args:
        dashboard_name: Name for the dashboard
        stack_name: CloudFormation stack name
        region: AWS region
        api_id: API Gateway REST API ID
        authorizer_function_name: Lambda Authorizer function name
    """
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    
    dashboard_body = create_dashboard_body(
        stack_name=stack_name,
        region=region,
        api_id=api_id,
        authorizer_function_name=authorizer_function_name
    )
    
    try:
        response = cloudwatch.put_dashboard(
            DashboardName=dashboard_name,
            DashboardBody=json.dumps(dashboard_body)
        )
        
        print(f"✓ Dashboard '{dashboard_name}' created successfully")
        print(f"  Dashboard ARN: {response.get('DashboardValidationMessages', 'N/A')}")
        print(f"  View at: https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#dashboards:name={dashboard_name}")
        
    except Exception as e:
        print(f"✗ Failed to create dashboard: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Create CloudWatch Dashboard for API Authentication Monitoring'
    )
    parser.add_argument(
        '--stack-name',
        required=True,
        help='CloudFormation stack name'
    )
    parser.add_argument(
        '--region',
        default=os.getenv('AWS_REGION', 'us-west-2'),
        help='AWS region (default: value of AWS_REGION env var or us-west-2)'
    )
    parser.add_argument(
        '--api-id',
        required=True,
        help='API Gateway REST API ID'
    )
    parser.add_argument(
        '--authorizer-function-name',
        required=True,
        help='Lambda Authorizer function name'
    )
    parser.add_argument(
        '--dashboard-name',
        help='Dashboard name (default: <stack-name>-auth-monitoring)'
    )
    
    args = parser.parse_args()
    
    dashboard_name = args.dashboard_name or f"{args.stack_name}-auth-monitoring"
    
    print(f"Creating CloudWatch Dashboard: {dashboard_name}")
    print(f"  Stack: {args.stack_name}")
    print(f"  Region: {args.region}")
    print(f"  API ID: {args.api_id}")
    print(f"  Authorizer: {args.authorizer_function_name}")
    print()
    
    create_dashboard(
        dashboard_name=dashboard_name,
        stack_name=args.stack_name,
        region=args.region,
        api_id=args.api_id,
        authorizer_function_name=args.authorizer_function_name
    )


if __name__ == '__main__':
    main()
