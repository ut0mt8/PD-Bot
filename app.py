from chalice import Chalice, Response
from urlparse import urlparse, parse_qs
from slackclient import SlackClient
import os
import json
import pypd
import hashlib
import hmac

app = Chalice(app_name='PD-Bot')

# TODO : handle multiple chan/services
mail = os.environ['PD_MAIL']

def verify_slack_request(signature, timestamp, data):
    signing_secret = os.environ['SC_SIGNING_KEY']
    req = str.encode('v0:' + str(timestamp) + ':') + data
    request_hash = 'v0=' + hmac.new( str.encode(signing_secret), req, hashlib.sha256).hexdigest()
    return hmac.compare_digest(bytes(request_hash), bytes(signature))


@app.route('/slack_callback', methods = ['POST'], content_types=['application/x-www-form-urlencoded'])
def sc_callback():
    try:
        pypd.api_key = os.environ['PD_API_KEY']
        event = app.current_request
        sc_signature = event.headers['X-Slack-Signature']
        sc_request_timestamp = event.headers['X-Slack-Request-Timestamp']
        if not verify_slack_request(sc_signature, sc_request_timestamp, event.raw_body):
            return Response("{'text':'Unauthorized'}", status_code=401)

        body = parse_qs(event.raw_body)
        payload = json.loads(body['payload'][0])
        cid = payload['callback_id']
        action = payload['actions'][0]['value']
        incident = pypd.Incident.fetch(cid)
        if action == "ack":
            incident.acknowledge(mail)
        elif action == "resolve":
            incident.resolve(mail)

        return Response("{'text':''}", status_code=200)

    except Exception as e:
        print e

    return Response("{'text':'Unauthorized'}", status_code=401)


@app.route('/pd_callback/{servicekey}', methods = ['POST'])
def pd_callback(servicekey):
    channel = os.environ['SC_CHAN']
    pd_url = "https://content-square.pagerduty.com/incidents/"
    graf_url = "https://grafana.eu-west-1.csq.io/d/e5Q3Ln1Wk/kafka-pipeline-overview?orgId=1&refresh=5m"
    doc_url = "https://contentsquare.atlassian.net/wiki/spaces/RD/pages/14975008/Data+Engineering"

    try:
        key = os.environ['PD_SVC_KEY']
        if key != servicekey:
            return Response("{'text':'Unauthorized'}", status_code=401)

        j = app.current_request.json_body
        event = j['messages'][0]['event']
        iid =  j['messages'][0]['incident']['id']
        summary =  j['messages'][0]['incident']['summary']
        urgency =  j['messages'][0]['incident']['urgency']
        lts =  j['messages'][0]['created_on']
        service =  j['messages'][0]['incident']['service']['name']
        assignee =  j['messages'][0]['incident']['assignments'][0]['assignee']['summary']

        pypd.api_key = os.environ['PD_API_KEY']
        sc_api_key = os.environ['SC_API_KEY']
        sc = SlackClient(sc_api_key)

        attachments=[{
              "title": "",
              "title_link": pd_url+iid,
              "color": "#fff",
              "attachment_type": "default",
              "callback_id": iid,
              "footer": "",
              "fields": [
                { "title": "", "value": "*Urgency:* "+urgency, "short": "true" },
                { "title": "", "value": "*Assigned:* "+assignee, "short": "true" }
              ],
              "mrkdwn_in": [
                "fields"
              ],
              "actions": []
        }]

        for link in  j['messages'][0]['log_entries'][0]['contexts']:
            if link['text'] == 'Grafana':
                graf_url = link['href']
            if link['text'] == 'Confluence':
                doc_url = link['href']

        def set_actions(graf_url, doc_url):
            return [
                { "name": "ack", "text": "Acknowledge", "type": "button", "value": "ack" },
                { "name": "resolve", "text": "Resolve", "type": "button", "value": "resolve" },
                { "text": "Grafana", "type": "button", "url": graf_url },
                { "text": "Confluence", "type": "button", "url": doc_url }
            ]

        if event == "incident.trigger":
            attachments[0]['title'] = "{} {}".format("Triggered", summary)
            if urgency == 'low':
                attachments[0]['color'] = "#ff4500"
            else:
                attachments[0]['color'] = "#b80f0A"
            attachments[0]['actions'] = set_actions(graf_url, doc_url)
            response = sc.api_call("chat.postMessage", as_user=True, channel=channel, text="", attachments=attachments)
            incident = pypd.Incident.fetch(iid)
            incident.create_note(mail, ','.join((response['channel'], response['ts'], graf_url, doc_url)))
        elif event == "incident.acknowledge":
            incident = pypd.Incident.fetch(iid)
            notes = incident.notes()
            (chan, ts, graf_url, doc_url) = notes[0]['content'].split(',')
            attachments[0]['title'] = "{} {}".format("Acknowledged", summary)
            attachments[0]['color'] = "#94b1b9"
            attachments[0]['actions'] = set_actions(graf_url, doc_url)
            attachments[0]['footer'] = "Acknowledged by {} ({})".format(assignee, lts)
            attachments[0]['footer_icon'] = "https://s3-us-west-2.amazonaws.com/pd-slack/icons/acked.png"
            sc.api_call("chat.update", ts=ts, channel=chan, as_user=True, text="", attachments=attachments)
        elif event == "incident.resolve":
            incident = pypd.Incident.fetch(iid)
            notes = incident.notes()
            (chan, ts, graf_url, doc_url) = notes[0]['content'].split(',')
            attachments[0]['title'] = "{} {}".format("Resolved", summary)
            attachments[0]['color'] = "#00a600"
            attachments[0]['footer'] = "Resolved ({})".format(lts)
            attachments[0]['footer_icon'] = "https://s3-us-west-2.amazonaws.com/pd-slack/icons/resolved.png"
            sc.api_call("chat.update", ts=ts, channel=chan, as_user=True, text="", attachments=attachments)

    except Exception as e:
        print e
        return Response("{'text':'Unauthorized'}", status_code=401)

    return Response("", status_code=202, headers={'Content-Type': 'text/html'})

