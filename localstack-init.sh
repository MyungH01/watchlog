#!/bin/sh
# LocalStack이 준비되면 실행된다. 운영 환경에서 Terraform이 만들 리소스의 로컬 대역.
set -e

awslocal s3 mb s3://watchlog-local
# 브라우저가 다른 주소(localhost:8000 → localhost:4566)로 직접 올리므로 CORS 허용이 필요하다
awslocal s3api put-bucket-cors --bucket watchlog-local --cors-configuration '{
  "CORSRules": [{"AllowedOrigins": ["*"], "AllowedMethods": ["POST", "GET"], "AllowedHeaders": ["*"]}]
}'

# 세 번 실패한 메시지는 격리 큐로 보낸다. 보이지 않는 시간은 분석 한 건의 최대 소요보다 길게.
awslocal sqs create-queue --queue-name watchlog-analysis-dlq
awslocal sqs create-queue --queue-name watchlog-analysis --attributes '{
  "VisibilityTimeout": "120",
  "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:ap-northeast-2:000000000000:watchlog-analysis-dlq\",\"maxReceiveCount\":\"3\"}"
}'
