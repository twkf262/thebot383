from flask import Flask, request
#from telegram import Bot
#from telegram.ext import CommandHandler, Updater, Dispatcher, Update, MessageHandler, Filters

import psycopg2, os, telegram, json, requests

app = Flask(__name__)

# This is the old 'hello world' code
#@app.route('/')
#def hello():
#    return "Hello, World!"

webhook_url_suffix = '/webhook'
webhook_url = os.getenv('WEBSERVICE_URL') + webhook_url_suffix
@app.route(webhook_url_suffix, methods=['POST'])

#telegram_bot_api_url = os.getenv('TELEGRAM_API_URL') + '/bot' + os.getenv('TELEGRAM_BOT_TOKEN')
telegram_bot_api_url = os.getenv('TELEGRAM_API_URL')
telegram_bot_api_url = telegram_bot_api_url + '/bot'
telegram_bot_api_url = telegram_bot_api_url + os.getenv('TELEGRAM_BOT_TOKEN')


app = Flask(__name__)

# Set webhook with Telegram
def set_telegram_webhook():
    response = requests.post(telegram_bot_api_url + '/setWebhook', data={'url': webhook_url})
    if response.status_code == 200:
        print("Webhook successfully set.")
    else:
        print("Failed to set webhook.", response.text)

def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json_str, bot)
    # Handle the update (e.g., respond to the bot message)

    print(update)  # Log the incoming update for debugging

    # Get message details
    message = update.get('message')
    if message:
        chat_id = message['chat']['id']
        text = message.get('text')

        # If a message exists, echo it back
        if text:
            send_message(chat_id, text)

    return 'OK', 200

def send_message(chat_id, text):
    #Send a message back to the user.
    url = telegram_bot_api_url + '/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        print("Message sent successfully.")
    else:
        print("Failed to send message.", response.text)

if __name__ == '__main__':
    app.run(debug=True)
#    app.run(debug=True, host='0.0.0.0', port=5000)

# Replace with your bot's token
bot = telegram.Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))

# Set the webhook to Render's URL
bot.set_webhook(url=os.getenv('WEBSERVICE_URL') + webhook_url_suffix)

# Connect to the PostgreSQL database using the connection string
conn = psycopg2.connect(os.getenv('DATABASE_URL'))

# Use a cursor to interact with the database
cursor = conn.cursor()

# Example: Insert data into the database
#cursor.execute("INSERT INTO users (user_id, username) VALUES (%s, %s)", (user_id, username))
conn.commit()

# Close the connection
cursor.close()
conn.close()
