import os
import slack
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, Response
from slackeventsapi import SlackEventAdapter
import string
from datetime import datetime, timedelta

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
slack_event_adapter = SlackEventAdapter(os.environ['SIGNING_SECRET'],'/slack/events',app)

client = slack.WebClient(token=os.environ['SLACK_TOKEN'])
# client.chat_postMessage(channel='#test', text="Hello You!")
BOT_ID = client.api_call("auth.test")['user_id']

message_counts = {}
welcome_messages = {}

BAD_WORDS = ['hmm', 'tim', 'no']

SCHEDULED_MESSAGES = [
    {'text':'First message','post_at': (datetime.now() + timedelta(seconds=40)).timestamp(),'channel':'C01H7HJ8NCF'},
    {'text': 'Second message','post_at': (datetime.now() + timedelta(seconds=50)).timestamp(),'channel':'C01H7HJ8NCF'},
]

def schedule_messages(messages):
    ids=[]
    for message in messages:
        response = client.chat_scheduleMessage(channel=message['channel'],text=message['text'], post_at=message['post_at'])
        id_ = response.get('scheduled_message_id')
        ids.append(id_)
        
    return ids

def delete_scheduled_messages(ids, channel):
    for _id in ids:
        try:
            client.chat_deleteScheduledMessage(
                channel=channel, scheduled_message_id=_id)
        except Exception as e:
            print(e)

def send_welcome_message(channel,user):
    if channel not in welcome_messages:
        welcome_messages[channel] = {}
        
    if user in welcome_messages[channel]:
        return
    
    welcome = WelcomeMessage(channel,user)
    message = welcome.get_message()
    response = client.chat_postMessage(**message)
    welcome.timestamp = response['ts']
    welcome_messages[channel][user] = welcome
    
def list_scheduled_messages(channel):
    response = client.chat_scheduledMessages_list(channel=channel)
    messages = response.data.get('scheduled_messages')
    ids = []
    for msg in messages:
        ids.append(msg.get('id'))

    return ids

class WelcomeMessage:
    START_TEXT = {
        'type' : 'section',
        'text' : {
            'type' : 'mrkdwn',
            'text' : (
                'Welcome to this slack channel! \n\n'
                '*Get started by completing the tasks!*'
            )
        }
    }
    
    DIVIDER = {'type' : 'divider'}
    
    def __init__(self,channel,user):
        self.channel = channel
        self.user = user
        self.icon_emoji = '🤖'
        self.timestamp = ''
        self.completed = False
        
    def get_message(self):
        return {
            'ts' : self.timestamp,
            'channel' : self.channel,
            'username' : 'Welcome',
            'icon_emoji' : self.icon_emoji,
            'blocks' : [
                self.START_TEXT,
                self.DIVIDER,
                self._get_reaction_task()
            ]
        }
    
    def _get_reaction_task(self):
        checkmark = ':white_check_mark:'
        if not self.completed:
            checkmark = ':white_large_square:'

        text = f'{checkmark} *React to this message!*'

        return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}}
    
def check_if_bad_words(message) :
    msg = message.lower()
    msg.translate(str.maketrans('','',string.punctuation))
    return any(word in msg for word in BAD_WORDS)

@slack_event_adapter.on('message')
def message(payload):
    event = payload.get('event', {})
    channel_id = event.get('channel')
    user_id = event.get('user')
    text = event.get('text')
    
    if user_id != BOT_ID :
        if user_id in message_counts:
            message_counts[user_id] += 1
        else :
            message_counts[user_id] = 1
        #client.chat_postMessage(channel=channel_id, text=text)
        
        if text.lower() == 'start':
            send_welcome_message(f'@{user_id}',user_id)
        elif check_if_bad_words(text):
            ts = event.get('ts')
            client.chat_postMessage(channel=channel_id, thread_ts=ts,text="That is a bad word!")
            
@slack_event_adapter.on('reaction_added')
def reaction(payload):
    event = payload.get('event', {})
    channel_id = event.get('item', {}).get('channel')
    user_id = event.get('user')
    
    if f'@{user_id}' not in welcome_messages:
        return
    
    welcome = welcome_messages[f'@{user_id}'][user_id]
    welcome.completed = True
    welcome.channel = channel_id
    message = welcome.get_message()
    updated_message = client.chat_update(**message)
    welcome.timestamp = updated_message['ts']
    
    
@app.route('/message-count', methods=['POST'])
def message_count():
    data = request.form
    channel_id = data.get('channel_id')
    user_id = data.get('user_id')
    message_count = message_counts.get(user_id,0)
    client.chat_postMessage(channel=channel_id, text=f"Message : {message_count}")
    return Response(), 200

if __name__ == "__main__" :
    schedule_messages(SCHEDULED_MESSAGES)
    ids = list_scheduled_messages('C01H7HJ8NCF')
    delete_scheduled_messages(ids,'C01H7HJ8NCF')
    app.run(debug=True)