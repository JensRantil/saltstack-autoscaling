SaltStack AWS autoscaling
=========================

This is a skeleton/example of one way to combine auto-scaling on AWS with a Salt(Stack) master.

Overall structure
-----------------
The overall requirement for this project is to

 1. have all autoscaled minions automatically accepted on the master. The way
    we distinguish these minions from other minions is through a unique prefix,
    `PLACEHOLDER_MINION_PREFIX`.
 2. never autoaccept a minion which has not been started through autoscaling.
    This is important for security!
 3. delete the minion key when the instance is terminated by the autoscale
    group.

A [Salt engine](https://docs.saltstack.com/en/2015.8/topics/engines/index.html),
`sqs_engine.py` (see `extensions/engines`), listens to an [AWS SQS](https://aws.amazon.com/sqs/) queue
(`PLACEHOLDER_AUTOSCALING_SQS_QUEUE`) which has been subscribed to an
[AWS SNS](https://aws.amazon.com/sns/) topic that your autoscaling group
publishes instance launches/terminations to.

`sqs_engine.py` republishes the SQS message on the Salt master event bus.
[Reactors](https://docs.saltstack.com/en/latest/topics/reactor/) trigger on the
SQS message. If an instance is launched, we store it in a small sqlite
database. If an instance is terminated, we remove its equivalent minion key.

When a minion with a `PLACEHOLDER_MINION_PREFIX` prefix connects, we store it
in the same above sqlite-database.

Iff 1) a minion has connected to us and 2) we've received a message from SQS
that it it is launched, our reactor accepts the minion and `state.highstate`s
it.

How to install this
-------------------
Search and replace all `PLACEHOLDER*` constants. See below for descriptions.
See README files in individual directories for details on where files need to
go.

Constants:

 * `PLACEHOLDER_AUTOSCALING_SQS_QUEUE`: The name of the SQS queue that auto
   scaling events are published to.
 * `PLACEHOLDER_MINION_PREFIX`: The prefix of the autoscaled minions. Could be
   "myworker" if you have a bunch of workers that are being autoscaled.
 * `PLACEHOLDER_MY_AWS_REGION`: The AWS region where your SQS queue lives.
 * `PLACEHOLDER_PATH_TO_REACTORS`: The directory where you keep you reactors in
   the file system.

A note about `sqs_engine`
-------------------------
I was unable to make the original `sqs_engine` engine that came with the
SaltStack project to work. This was probably mostly due to the fact that I was
using an older version of `boto`, version 2.2.2, which didn't support role
based authentication, nor custom long-polling timeouts. I was also having
issues with JSON decoding. That's why this repository ships with its own
engine. I'll see if I can get any of my changes merged upstream.

Who are you?
------------
I'm [Jens Rantil](http://jensrantil.github.io/), a backend engineer at
[Tink](https://www.tinkapp.com).
