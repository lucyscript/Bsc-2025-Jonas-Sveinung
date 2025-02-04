# Mock Testing

## To test the webhook POST locally

curl -X POST \
 http://127.0.0.1:8000/webhook \
 -H "Content-Type: application/json" \
 -d '{"text": "The Earth is flat", "language": "en", "context": "Some context"}'

## To test the fact-check POST locally

curl -X POST \
 http://127.0.0.1:8000/fact-check/check \
 -H "Content-Type: application/json" \
 -d '{"text": "The Earth is flat"}'

## To test via fly.io

curl -X POST https://whatsapp-fact-checking-bot.fly.dev/webhook \
 -H "Content-Type: application/json" \
 -d '{
"object": "whatsapp_business_account",
"entry": [{
"id": "532790276588326",
"changes": [{
"value": {
"messaging_product": "whatsapp",
"metadata": {
"display_phone_number": "15551835357",
"phone_number_id": "546423465222677"
},
"contacts": [{
"profile": {"name": "Sveinung"},
"wa_id": "4741377260"
}],
"messages": [{
"from": "4741377260",
"id": "wamid.sample.id",
"timestamp": "1738853946",
"text": {"body": "The Earth is flat"},
"type": "text"
}]
},
"field": "messages"
}]
}]
}'
