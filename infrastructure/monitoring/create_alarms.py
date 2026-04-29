#!/usr/bin/env python3
"""
Create CloudWatch Alarms for API Authentication and Authorization Monitoring.

This script creates CloudWatch alarms for:
- High authentication failure rate
- Authorization errors
- Unusual access patterns
- Lambda authorizer errors

Requirements: 4.5, 4.6
"""

import boto3
import sys
from typing import List, Dict, Any


def create_authentication_failure_alarm(
    cloudwatch: Any,
    alarm_name_prefix: str,
    authorizer_function_name: str,
    sns_topic_arn: str,
    region: str
) -> None:
    """
    Create alarm for high authentication failure rate.
    
    Triggers when authentication failures exceed 10 in 5 minutes.
    
    Args:
        cloudwatch: CloudWatch client
        alarm_name_prefix: Prefix for alarm names
        authorizer_function_name: Lambda Authorizer function name
        sns_topic_arn: SNS topic ARN for notifications
        region: AWS region
    """
    alarm_name = f"{alarm_name_prefix}-high-auth-failures"
    
    # Create metric filter if it doesn't exist
    logs = boto3.client('logs', region_name=region)
    log_group_name = f"/aws/lambda/{authorizer_function_name}"
    filter_name = "AuthenticationFailures"
    
    try:
        logs.put_metric_filter(
            logGroupName=log_group_name,
            filterName=filter_name,
            filterPattern='{ $.event_type = "AUTHENTICATION_FAILURE" }',
            metricTransformations=[
                {
                    'metricName': 'AuthenticationFailures',
                    'metricNamespace': 'OrdersAPI/Authentication',
                    'metricValue': '1',
                    'defaultValue': 0
                }
            ]
        )
        print(f"✓ Metric filter '{filter_name}' created/updated")
    except Exception as e:
        print(f"⚠ Warning: Could not create metric filter: {e}")
    
    # Create alarm
    try:
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            AlarmDescription='Triggers when authentication failures exceed threshold',
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn] if sns_topic_arn else [],
            MetricName='AuthenticationFailures',
            Namespace='OrdersAPI/Authentication',
            Statistic='Sum',
            Period=300,  # 5 minutes
            EvaluationPeriods=1,
            Threshold=10.0,
            ComparisonOperator='GreaterThanThreshold',
            TreatMissingData='notBreaching'
        )
        print(f"✓ Alarm '{alarm_name}' created successfully")
    except Exception as e:
        print(f"✗ Failed to create alarm '{alarm_name}': {e}", file=sys.stderr)


def create_authorization_error_alarm(
    cloudwatch: Any,
    alarm_name_prefix: str,
    authorizer_function_name: str,
    sns_topic_arn: str,
    region: str
) -> None:
    """
    Create alarm for authorization errors.
    
    Triggers when authorization errors occur (system errors, not denials).
    
    Args:
        cloudwatch: CloudWatch client
        alarm_name_prefix: Prefix for alarm names
        authorizer_function_name: Lambda Authorizer function name
        sns_topic_arn: SNS topic ARN for notifications
        region: AWS region
    """
    alarm_name = f"{alarm_name_prefix}-authorization-errors"
    
    # Create metric filter
    logs = boto3.client('logs', region_name=region)
    log_group_name = f"/aws/lambda/{authorizer_function_name}"
    filter_name = "AuthorizationErrors"
    
    try:
        logs.put_metric_filter(
            logGroupName=log_group_name,
            filterName=filter_name,
            filterPattern='{ $.event_type = "AUTHORIZATION_ERROR" }',
            metricTransformations=[
                {
                    'metricName': 'AuthorizationErrors',
                    'metricNamespace': 'OrdersAPI/Authorization',
                    'metricValue': '1',
                    'defaultValue': 0
                }
            ]
        )
        print(f"✓ Metric filter '{filter_name}' created/updated")
    except Exception as e:
        print(f"⚠ Warning: Could not create metric filter: {e}")
    
    # Create alarm
    try:
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            AlarmDescription='Triggers when authorization system errors occur',
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn] if sns_topic_arn else [],
            MetricName='AuthorizationErrors',
            Namespace='OrdersAPI/Authorization',
            Statistic='Sum',
            Period=300,  # 5 minutes
            EvaluationPeriods=1,
            Threshold=5.0,
            ComparisonOperator='GreaterThanThreshold',
            TreatMissingData='notBreaching'
        )
        print(f"✓ Alarm '{alarm_name}' created successfully")
    except Exception as e:
        print(f"✗ Failed to create alarm '{alarm_name}': {e}", file=sys.stderr)


def create_lambda_error_alarm(
    cloudwatch: Any,
    alarm_name_prefix: str,
    authorizer_function_name: str,
    sns_topic_arn: str,
    region: str
) -> None:
    """
    Create alarm for Lambda authorizer errors.
    
    Triggers when Lambda function errors occur.
    
    Args:
        cloudwatch: CloudWatch client
        alarm_name_prefix: Prefix for alarm names
        authorizer_function_name: Lambda Authorizer function name
        sns_topic_arn: SNS topic ARN for notifications
        region: AWS region
    """
    alarm_name = f"{alarm_name_prefix}-lambda-errors"
    
    try:
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            AlarmDescription='Triggers when Lambda Authorizer function errors occur',
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn] if sns_topic_arn else [],
            MetricName='Errors',
            Namespace='AWS/Lambda',
            Dimensions=[
                {
                    'Name': 'FunctionName',
                    'Value': authorizer_function_name
                }
            ],
            Statistic='Sum',
            Period=300,  # 5 minutes
            EvaluationPeriods=1,
            Threshold=5.0,
            ComparisonOperator='GreaterThanThreshold',
            TreatMissingData='notBreaching'
        )
        print(f"✓ Alarm '{alarm_name}' created successfully")
    except Exception as e:
        print(f"✗ Failed to create alarm '{alarm_name}': {e}", file=sys.stderr)


def create_unusual_access_pattern_alarm(
    cloudwatch: Any,
    alarm_name_prefix: str,
    authorizer_function_name: str,
    sns_topic_arn: str,
    region: str
) -> None:
    """
    Create alarm for unusual access patterns.
    
    Triggers when authorization denials spike (potential attack).
    
    Args:
        cloudwatch: CloudWatch client
        alarm_name_prefix: Prefix for alarm names
        authorizer_function_name: Lambda Authorizer function name
        sns_topic_arn: SNS topic ARN for notifications
        region: AWS region
    """
    alarm_name = f"{alarm_name_prefix}-unusual-access-pattern"
    
    # Create metric filter
    logs = boto3.client('logs', region_name=region)
    log_group_name = f"/aws/lambda/{authorizer_function_name}"
    filter_name = "AuthorizationDenials"
    
    try:
        logs.put_metric_filter(
            logGroupName=log_group_name,
            filterName=filter_name,
            filterPattern='{ $.event_type = "AUTHORIZATION_ATTEMPT" && $.decision = "DENY" }',
            metricTransformations=[
                {
                    'metricName': 'AuthorizationDenials',
                    'metricNamespace': 'OrdersAPI/Authorization',
                    'metricValue': '1',
                    'defaultValue': 0
                }
            ]
        )
        print(f"✓ Metric filter '{filter_name}' created/updated")
    except Exception as e:
        print(f"⚠ Warning: Could not create metric filter: {e}")
    
    # Create alarm
    try:
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            AlarmDescription='Triggers when authorization denials spike (potential attack)',
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn] if sns_topic_arn else [],
            MetricName='AuthorizationDenials',
            Namespace='OrdersAPI/Authorization',
            Statistic='Sum',
            Period=300,  # 5 minutes
            EvaluationPeriods=2,  # 2 consecutive periods
            Threshold=20.0,
            ComparisonOperator='GreaterThanThreshold',
            TreatMissingData='notBreaching'
        )
        print(f"✓ Alarm '{alarm_name}' created successfully")
    except Exception as e:
        print(f"✗ Failed to create alarm '{alarm_name}': {e}", file=sys.stderr)


def create_lambda_throttle_alarm(
    cloudwatch: Any,
    alarm_name_prefix: str,
    authorizer_function_name: str,
    sns_topic_arn: str,
    region: str
) -> None:
    """
    Create alarm for Lambda throttling.
    
    Triggers when Lambda authorizer is being throttled.
    
    Args:
        cloudwatch: CloudWatch client
        alarm_name_prefix: Prefix for alarm names
        authorizer_function_name: Lambda Authorizer function name
        sns_topic_arn: SNS topic ARN for notifications
        region: AWS region
    """
    alarm_name = f"{alarm_name_prefix}-lambda-throttles"
    
    try:
        cloudwatch.put_metric_alarm(
            AlarmName=alarm_name,
            AlarmDescription='Triggers when Lambda Authorizer is being throttled',
            ActionsEnabled=True,
            AlarmActions=[sns_topic_arn] if sns_topic_arn else [],
            MetricName='Throttles',
            Namespace='AWS/Lambda',
            Dimensions=[
                {
                    'Name': 'FunctionName',
                    'Value': authorizer_function_name
                }
            ],
            Statistic='Sum',
            Period=300,  # 5 minutes
            EvaluationPeriods=1,
            Threshold=1.0,
            ComparisonOperator='GreaterThanThreshold',
            TreatMissingData='notBreaching'
        )
        print(f"✓ Alarm '{alarm_name}' created successfully")
    except Exception as e:
        print(f"✗ Failed to create alarm '{alarm_name}': {e}", file=sys.stderr)


def create_all_alarms(
    alarm_name_prefix: str,
    authorizer_function_name: str,
    region: str,
    sns_topic_arn: str = None
) -> None:
    """
    Create all CloudWatch alarms.
    
    Args:
        alarm_name_prefix: Prefix for alarm names
        authorizer_function_name: Lambda Authorizer function name
        region: AWS region
        sns_topic_arn: Optional SNS topic ARN for notifications
    """
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    
    print("Creating CloudWatch Alarms...")
    print()
    
    # Create all alarms
    create_authentication_failure_alarm(
        cloudwatch, alarm_name_prefix, authorizer_function_name, sns_topic_arn, region
    )
    
    create_authorization_error_alarm(
        cloudwatch, alarm_name_prefix, authorizer_function_name, sns_topic_arn, region
    )
    
    create_lambda_error_alarm(
        cloudwatch, alarm_name_prefix, authorizer_function_name, sns_topic_arn, region
    )
    
    create_unusual_access_pattern_alarm(
        cloudwatch, alarm_name_prefix, authorizer_function_name, sns_topic_arn, region
    )
    
    create_lambda_throttle_alarm(
        cloudwatch, alarm_name_prefix, authorizer_function_name, sns_topic_arn, region
    )
    
    print()
    print("✓ All alarms created successfully")
    print(f"  View at: https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#alarmsV2:")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Create CloudWatch Alarms for API Authentication Monitoring'
    )
    parser.add_argument(
        '--stack-name',
        required=True,
        help='CloudFormation stack name (used as alarm prefix)'
    )
    parser.add_argument(
        '--region',
        default=os.getenv('AWS_REGION', 'us-west-2'),
        help='AWS region (default: value of AWS_REGION env var or us-west-2)'
    )
    parser.add_argument(
        '--authorizer-function-name',
        required=True,
        help='Lambda Authorizer function name'
    )
    parser.add_argument(
        '--sns-topic-arn',
        help='SNS topic ARN for alarm notifications (optional)'
    )
    
    args = parser.parse_args()
    
    print(f"Creating CloudWatch Alarms for: {args.stack_name}")
    print(f"  Region: {args.region}")
    print(f"  Authorizer: {args.authorizer_function_name}")
    if args.sns_topic_arn:
        print(f"  SNS Topic: {args.sns_topic_arn}")
    else:
        print(f"  SNS Topic: None (alarms will not send notifications)")
    print()
    
    create_all_alarms(
        alarm_name_prefix=args.stack_name,
        authorizer_function_name=args.authorizer_function_name,
        region=args.region,
        sns_topic_arn=args.sns_topic_arn
    )


if __name__ == '__main__':
    main()
