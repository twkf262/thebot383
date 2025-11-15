from flask import Flask, request
from telegram import Bot
from telegram.ext import CommandHandler, Updater

import os
import telegram

app = Flask(__name__)

# This is the old 'hello world' code
#@app.route('/')
#def hello():
#    return "Hello, World!"

@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json_str, bot)
    # Handle the update (e.g., respond to the bot message)
    return 'OK'

if __name__ == '__main__':
    app.run(debug=True)

# Replace with your bot's token
bot = telegram.Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))

# Set the webhook to Render's URL
webhook_url = token=os.getenv('WEBHOOK_URL')
bot.set_webhook(url=webhook_url)
