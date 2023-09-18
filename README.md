# df23_session_hijacking
## Sample code from Dreamforce 23 - [Actionable Insights: The Power of Real-Time Events](https://reg.salesforce.com/flow/plus/df23/sessioncatalog/page/catalog/session/1690384804706001a7az)

## Overview
This Python project highlights how to use the Salesforce LightningUriEventStream Pub/Sub API event to identify scenarios where attackers may be using stolen session cookies to impersonate a Salesforce user. It is important to mitigate this type of attack by requiring the use of the HttpOnly cookie attribute in your org's session settings.

This trivial demo looks only at the **DeviceSessionId** attribute of the LightningUriEventStream event. If different events with the same **LoginKey** have different DeviceSessionIds, we call it a session hijacking event. In real life you would want to pair that with a change in **OsName**, **OsVersion**, or **UserAgent**.

You will also want to consider scalability aspects. Please see the num_requested configuration on line 25, and [Pull Subscription and Flow Control](https://developer.salesforce.com/docs/platform/pub-sub-api/guide/flow-control.html) in the Salesforce documentation. A suggested practice is to avoid performing time-intensive processing within the program, and instead to place events on an internal message queue that has multiple subscribers.

The main program is session_hijack.py. In order to run this, you will need to add valid OAuth and credential information to the credentials.py module.
