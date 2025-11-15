from flask import Flask, request
from telegram import Bot
from telegram.ext import CommandHandler, Updater, Dispatcher, Update, MessageHandler, Filters

import psycopg2
import os
import telegram

app = Flask(__name__)

# This is the old 'hello world' code
#@app.route('/')
#def hello():
#    return "Hello, World!"

# Create a dispatcher for handling Telegram updates
def start(update, context):
    update.message.reply_text("Hello! Send me a message and I'll echo it.")

def echo(update, context):
# Echoes the message received from the user.
    message_text = update.message.text  # Extract the message text
    update.message.reply_text(message_text)  # Send the same text back to the user

# Set up the dispatcher with handlers
dispatcher = Dispatcher(bot, None, workers=0)

# Add handlers for the '/start' command and all text messages
dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

webhook_url_suffix = '/webhook'
@app.route(webhook_url_suffix, methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json_str, bot)
    # Handle the update (e.g., respond to the bot message)
    dispatcher.process_update(update)
    
    return 'OK'

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
