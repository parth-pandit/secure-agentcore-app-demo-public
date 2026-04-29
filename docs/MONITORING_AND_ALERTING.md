# Monitoring and Alerting Guide

This document describes the monitoring and alerting setup for the Orders API authentication and authorization system.

## Overview

The monitoring system provides visibility into:
- Authentication attempts and failures
- Authorization decisions (allow/deny)
- System errors and performance
- Unusual access patterns

## CloudWatch Dashboard

### Creating the Dashboard

The CloudWatch dashboard provides a comprehensive view of authentication and authorization metrics.

```bash
# Create the dashboard
python infrastructure/monitoring/create_dashboard.py \
  --stack-name dev-orders-api \
  --region us-west-2 \
  --api-id <your-api-id> \
  --authorizer-function-name dev-orders-api-authorizer
```

### Dashboard Widgets

The dashboard includes the following widgets:

#### 1. API Gateway - Request Overview
- **Metrics**: Total requests, 4XX errors, 5XX errors
- **Purpose**: Monitor overall API health
- **Period**: 5 minutes

#### 2. Lambda Authorizer - Invocations
- **Metrics**: Invocations, errors, throttles
- **Purpose**: Monitor authorizer function health
- **Period**: 5 minutes

#### 3. Lambda Authorizer - Duration
- **Metrics**: Average and maximum duration
- **Purpose**: Monitor authorizer performance
- **Period**: 5 minutes
- **Threshold**: Should stay under 3 seconds (requirement 9.4)

#### 4. Authentication Successes
- **Source**: CloudWatch Logs Insights query
- **Purpose**: Track successful authentications
- **Period**: 5 minutes

#### 5. Authentication Failures
- **Source**: CloudWatch Logs Insights query
- **Purpose**: Track failed authentication attempts
- **Period**: 5 minutes
- **Alert Threshold**: >10 failures in 5 minutes

#### 6. Authorization Allowed
- **Source**: CloudWatch Logs Insights query
- **Purpose**: Track successful authorization decisions
- **Period**: 5 minutes

#### 7. Authorization Denied
- **Source**: CloudWatch Logs Insights query
- **Purpose**: Track denied authorization attempts
- **Period**: 5 minutes
- **Alert Threshold**: >20 denials in 10 minutes (unusual pattern)

#### 8. Recent Authentication Failures
- **Type**: Log table
- **Purpose**: View details of recent authentication failures
- **Limit**: Last 20 entries

#### 9. Recent Authorization Denials
- **Type**: Log table
- **Purpose**: View details of recent authorization denials
- **Limit**: Last 20 entries

#### 10. Recent Errors
- **Type**: Log table
- **Purpose**: View system errors and authorization errors
- **Limit**: Last 20 entries

## CloudWatch Alarms

### Creating Alarms

```bash
# Create all alarms
python infrastructure/monitoring/create_alarms.py \
  --stack-name dev-orders-api \
  --region us-west-2 \
  --authorizer-function-name dev-orders-api-authorizer \
  --sns-topic-arn arn:aws:sns:us-west-2:123456789012:security-alerts
```

### Alarm Definitions

#### 1. High Authentication Failures
- **Metric**: AuthenticationFailures (custom metric from logs)
- **Threshold**: >10 failures in 5 minutes
- **Evaluation**: 1 period
- **Purpose**: Detect potential brute force attacks or configuration issues
- **Action**: Investigate failed authentication reasons in logs

#### 2. Authorization Errors
- **Metric**: AuthorizationErrors (custom metric from logs)
- **Threshold**: >5 errors in 5 minutes
- **Evaluation**: 1 period
- **Purpose**: Detect system errors in authorization logic
- **Action**: Check Lambda logs for error details and stack traces

#### 3. Lambda Errors
- **Metric**: AWS/Lambda Errors
- **Threshold**: >5 errors in 5 minutes
- **Evaluation**: 1 period
- **Purpose**: Detect Lambda function failures
- **Action**: Check Lambda logs and function configuration

#### 4. Unusual Access Pattern
- **Metric**: AuthorizationDenials (custom metric from logs)
- **Threshold**: >20 denials in 10 minutes (2 consecutive periods)
- **Evaluation**: 2 periods
- **Purpose**: Detect potential unauthorized access attempts
- **Action**: Review denied access attempts and user patterns

#### 5. Lambda Throttles
- **Metric**: AWS/Lambda Throttles
- **Threshold**: >1 throttle in 5 minutes
- **Evaluation**: 1 period
- **Purpose**: Detect Lambda concurrency limits being reached
- **Action**: Review Lambda concurrency settings and consider increasing limits

## Available Metrics

### Standard AWS Metrics

#### API Gateway
- `AWS/ApiGateway/Count`: Total number of API requests
- `AWS/ApiGateway/4XXError`: Client errors (401, 403, etc.)
- `AWS/ApiGateway/5XXError`: Server errors
- `AWS/ApiGateway/Latency`: API response time

#### Lambda
- `AWS/Lambda/Invocations`: Number of Lambda invocations
- `AWS/Lambda/Errors`: Number of Lambda errors
- `AWS/Lambda/Duration`: Lambda execution time
- `AWS/Lambda/Throttles`: Number of throttled invocations
- `AWS/Lambda/ConcurrentExecutions`: Concurrent executions

### Custom Metrics (from Logs)

#### OrdersAPI/Authentication
- `AuthenticationFailures`: Count of authentication failures
- **Source**: Log filter on `event_type = "AUTHENTICATION_FAILURE"`

#### OrdersAPI/Authorization
- `AuthorizationErrors`: Count of authorization system errors
- **Source**: Log filter on `event_type = "AUTHORIZATION_ERROR"`
- `AuthorizationDenials`: Count of authorization denials
- **Source**: Log filter on `event_type = "AUTHORIZATION_ATTEMPT" && decision = "DENY"`

## Log Queries

### Useful CloudWatch Logs Insights Queries

#### Authentication Failure Analysis
```
fields @timestamp, @message
| filter @message like /AUTHENTICATION_FAILURE/
| parse @message /reason: "(?<reason>[^"]+)"/
| stats count() by reason
| sort count desc
```

#### Authorization Denial by User
```
fields @timestamp, @message
| filter @message like /AUTHORIZATION_ATTEMPT/ and @message like /DENY/
| parse @message /user_email: "(?<user>[^"]+)"/
| parse @message /resource: "(?<resource>[^"]+)"/
| stats count() by user, resource
| sort count desc
```

#### Top Failed Authentication Sources
```
fields @timestamp, @message
| filter @message like /AUTHENTICATION_FAILURE/
| parse @message /source_ip: "(?<ip>[^"]+)"/
| stats count() by ip
| sort count desc
| limit 10
```

#### Authorization Performance
```
fields @timestamp, @message
| filter @message like /Lambda Authorizer invoked/
| stats avg(@duration), max(@duration), min(@duration)
```

## Alarm Thresholds

### Recommended Thresholds

| Alarm | Threshold | Rationale |
|-------|-----------|-----------|
| Authentication Failures | >10 in 5 min | Normal failed logins should be rare; spike indicates attack |
| Authorization Errors | >5 in 5 min | System errors should be very rare; indicates bug |
| Lambda Errors | >5 in 5 min | Function errors indicate code or configuration issues |
| Authorization Denials | >20 in 10 min | Sustained denials indicate unauthorized access attempts |
| Lambda Throttles | >1 in 5 min | Any throttling indicates capacity issues |

### Adjusting Thresholds

Thresholds should be adjusted based on:
- **Normal traffic patterns**: Higher traffic may need higher thresholds
- **User base size**: More users = more expected failures
- **Security posture**: Stricter security may warrant lower thresholds
- **False positive rate**: Adjust to reduce alert fatigue

## Incident Response Procedures

### High Authentication Failures

**Symptoms**: >10 authentication failures in 5 minutes

**Investigation Steps**:
1. Check CloudWatch Logs for failure reasons
2. Identify if failures are from single user or multiple users
3. Check if failures are from single IP or distributed
4. Review recent IAM Identity Center changes

**Possible Causes**:
- Brute force attack
- User credential issues
- IAM Identity Center configuration change
- Token expiration issues

**Actions**:
- If attack: Consider rate limiting or IP blocking
- If user issue: Contact affected users
- If configuration: Review and fix IAM IdC settings

### Authorization Errors

**Symptoms**: >5 authorization errors in 5 minutes

**Investigation Steps**:
1. Check Lambda logs for error stack traces
2. Review recent code or configuration changes
3. Check authorization policy configuration
4. Verify environment variables are set correctly

**Possible Causes**:
- Bug in authorization logic
- Malformed authorization policy
- Missing environment variables
- IAM permission issues

**Actions**:
- Review and fix code if bug found
- Validate authorization policy format
- Verify all required environment variables
- Check Lambda IAM role permissions

### Unusual Access Pattern

**Symptoms**: >20 authorization denials in 10 minutes

**Investigation Steps**:
1. Identify users being denied access
2. Check resources being accessed
3. Review authorization policies
4. Check for pattern in denied requests

**Possible Causes**:
- Unauthorized access attempt
- User permission misconfiguration
- Application bug causing invalid requests
- Legitimate user with insufficient permissions

**Actions**:
- If attack: Monitor and consider blocking
- If misconfiguration: Update authorization policies
- If bug: Fix application code
- If legitimate: Grant appropriate permissions

### Lambda Throttles

**Symptoms**: Lambda authorizer being throttled

**Investigation Steps**:
1. Check current Lambda concurrency settings
2. Review API request rate
3. Check if caching is working properly
4. Verify cache TTL settings

**Possible Causes**:
- Traffic spike exceeding Lambda capacity
- Cache not working (every request hits Lambda)
- Insufficient reserved concurrency
- DDoS attack

**Actions**:
- Increase Lambda reserved concurrency
- Verify API Gateway caching is enabled
- Check cache TTL (should be 300 seconds)
- Consider rate limiting if attack

## Best Practices

### Monitoring

1. **Review dashboard daily**: Check for anomalies in authentication/authorization patterns
2. **Set up SNS notifications**: Ensure alarms notify the right team
3. **Tune thresholds**: Adjust based on actual traffic patterns
4. **Regular log reviews**: Periodically review audit logs for security events
5. **Performance monitoring**: Ensure authorizer stays under 3-second requirement

### Alerting

1. **Avoid alert fatigue**: Set thresholds to minimize false positives
2. **Prioritize alerts**: Critical alerts should page on-call, warnings can wait
3. **Document runbooks**: Each alarm should have clear response procedures
4. **Test alerts**: Periodically test that alerts are working
5. **Review and improve**: Regularly review incident responses and improve procedures

### Security

1. **Monitor for patterns**: Look for unusual access patterns that might indicate attacks
2. **Track failed attempts**: High failure rates may indicate brute force attacks
3. **Review denials**: Regular authorization denials from same user may indicate misconfiguration
4. **Audit regularly**: Review audit logs for compliance and security
5. **Respond quickly**: Investigate and respond to security alerts promptly

## Troubleshooting

### Dashboard Not Showing Data

**Problem**: Dashboard widgets show no data

**Solutions**:
- Verify Lambda function name is correct
- Check that Lambda function has been invoked
- Verify log group exists: `/aws/lambda/<function-name>`
- Wait 5-10 minutes for metrics to populate
- Check CloudWatch Logs Insights query syntax

### Alarms Not Triggering

**Problem**: Alarms don't trigger when they should

**Solutions**:
- Verify metric filters are created correctly
- Check that log group name matches Lambda function
- Verify filter patterns match log format
- Check alarm threshold and evaluation period settings
- Ensure SNS topic ARN is correct (if using notifications)

### Missing Metrics

**Problem**: Custom metrics not appearing

**Solutions**:
- Verify metric filters are created in CloudWatch Logs
- Check that logs contain expected event types
- Verify log format matches filter pattern
- Wait 5-10 minutes for metrics to appear
- Check metric namespace and name

### High False Positive Rate

**Problem**: Alarms triggering too frequently

**Solutions**:
- Increase alarm thresholds
- Increase evaluation periods
- Adjust metric period (e.g., 5 min to 10 min)
- Review normal traffic patterns
- Consider using anomaly detection instead of static thresholds

## Additional Resources

- [CloudWatch Logs Insights Query Syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html)
- [CloudWatch Alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html)
- [Lambda Metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html)
- [API Gateway Metrics](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-metrics-and-dimensions.html)

## Requirements Validated

This monitoring and alerting setup validates the following requirements:
- **Requirement 4.5**: CloudWatch Logs storage with retention policies
- **Requirement 4.6**: Support for filtering logs by user, endpoint, timestamp, and outcome
- **Requirement 9.4**: Monitor that Lambda Authorizer completes within 3 seconds
