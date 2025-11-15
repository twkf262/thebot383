from flask import Flask, request
from telegram import Bot
from telegram.ext import CommandHandler, Updater

import psycopg2
import os
import telegram

app = Flask(__name__)

# This is the old 'hello world' code
#@app.route('/')
#def hello():
#    return "Hello, World!"

webhook_url_suffix = '/webhook'
@app.route(webhook_url_suffix, methods=['POST'])
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
