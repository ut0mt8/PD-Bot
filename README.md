Pagerduty Slack Bot replacement (chalice framework => aws lambda)

The main motivation is to remove the artificial limitation to have one personnal PD account for interracting with the bot. For example we can use an
account per team and everyone in the channel can ack or resolve incidents.

Other features are the possibility to directly show links added to incidents. Obviously we can customize the message. The default one mimic the PD app.

Every environment variables should be filled in .chalice/config.json.

Enjoy.
