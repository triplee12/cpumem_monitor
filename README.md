# Case Study: Application Performance Monitoring

With the modern, containerized, microservice-based deployment practices of today, some things that used to be trivial, such as monitoring your apps’ CPU and memory
usage, have become somewhat more complicated than just running top. Several commercial products have emerged over the last few years to deal with these problems,
but their cost can be prohibitive for small startup teams and hobbyists.
In this case study, I’ll exploit ØMQ and asyncio to build a toy prototype for distributed application monitoring. Our design has three parts:

- Application layer
    This layer contains all our applications. Examples might be a “customers” micro‐
    service, a “bookings” microservice, an “emailer” microservice, and so on. I will
    add a ØMQ “transmitting” socket to each of our applications. This socket will
    send performance metrics to a central server.

- Collection layer
    The central server will expose a ØMQ socket to collect the data from all the run‐
    ning application instances. The server will also serve a web page to show perfor‐
    mance graphs over time and will live-stream the data as it comes in.

- Visualization layer
    This is the web page being served. We’ll display the collected data in a set of
    charts, and the charts will live-update in real time. To simplify the code samples, I
    will use the convenient [Smoothie Charts](http://smoothiecharts.org) JavaScript library, which provides all the necessary client-side features.

## Codes Explanation For The app_layer.py

This coroutine function will run as a long-lived coroutine, continually sending out data to the server process.

Create a ØMQ socket. As you know, there are different flavors of socket; this one is a PUB type, which allows one-way messages to be sent to another ØMQ socket.
This socket has—as the ØMQ guide says—superpowers. It will automatically handle all reconnection and buffering logic for us.

Connect to the server.

Our shutdown sequence is driven by KeyboardInterrupt, farther down. When that signal is received, all the tasks will be cancelled. Here I handle the raised
CancelledError with the handy suppress() context manager from the context lib standard library module.

Iterate forever, sending out data to the server.

Since ØMQ knows how to work with complete messages, and not just chunks off a bytestream, it opens the door to a bunch of useful wrappers around the usual sock.send() idiom: here, I use one of those helper methods, send_json(), which will automatically serialize the argument into JSON. This allows us to use a dict() directly.

A reliable way to transmit datetime information is via the ISO 8601 format. This is especially true if you have to pass datetime data between software written in
different languages, since the vast majority of language implementations will be able to work with this standard.

To end up here, we must have received the CancelledError exception resulting from task cancellation. The ØMQ socket must be closed to allow program shutdown.

The main() function symbolizes the actual microservice application. Fake work is produced with this sum over random numbers, just to give us some nonzero data to view in the visualization layer a bit later.

I’m going to create multiple instances of this application, so it will be convenient to be able to distinguish between them (later, in the graphs) with a --color parameter.

Finally, the ØMQ context can be terminated.

The primary point of interest is the stats_reporter() function. This is what streams out metrics data (collected by the useful psutil library). The rest of the code can be assumed to be a typical microservice application.

## Codes Explanation For collect_layer.py

One half of this program will receive data from other applications, and the other half will provide data to browser clients via server-sent events (SSEs). I use a
WeakSet() to keep track of all the currently connected web clients. Each connected client will have an associated Queue() instance, so this connections identifier is really a set of queues.

Recall that in the application layer, I used a zmq.PUB socket; here in the collection layer, I use its partner, the zmq.SUB socket type. This ØMQ socket can only receive, not send.

For the zmq.SUB socket type, providing a subscription name is required, but for our purposes, we’ll just take everything that comes in—hence the empty topic name.

I bind the zmq.SUB socket. Think about that for second. In pub-sub configurations, you usually have to make the pub end the server (bind()) and the sub end the client (connect()). ØMQ is different: either end can be the server. For our use case, this is important, because each of our application-layer instances will be
connecting to the same collection server domain name, and not the other way around.

The support for asyncio in pyzmq allows us to await data from our connected apps. And not only that, but the incoming data will be automatically deserialized from JSON (yes, this means data is a dict()).

Recall that our connections set holds a queue for every connected web client.
Now that data has been received, it’s time to send it to all the clients: the data is placed onto each queue.

The feed() coroutine function will create coroutines for each connected web client. Internally, [server-sent events](https://mzl.la/2omEs3t) are used to push data to the web clients.

As described earlier, each web client will have its own queue instance, in order to receive data from the collector() coroutine. The queue instance is added to the
connections set, but because connections is a weak set, the entry will automatically be removed from connections when the queue goes out of scope—i.e., when a web client disconnects. [Weakrefs](https://oreil.ly/fRmdu) are great for simplifying these kinds of bookkeeping tasks.

The aiohttp_sse package provides the sse_response() context manager. This gives us a scope inside which to push data to the web client.

We remain connected to the web client, and wait for data on this specific client’s queue.

As soon as the data comes in (inside collector()), it will be sent to the connected web client. Note that I reserialize the data dict here. An optimization to this
code would be to avoid deserializing JSON in collector(), and instead use sock.recv_string() to avoid the serialization round trip. Of course, in a real scenario, you might want to deserialize in the collector, and perform some validation on the data before sending it to the browser client. So many choices!

The index() endpoint is the primary page load, and here we serve a static file called charts.html.

The aiohttp library provides facilities for us to hook in additional long-lived coroutines we might need. With the collector() coroutine, we have exactly that situation, so I create a startup coroutine, start_collector(), and a shutdown coroutine. These will be called during specific phases of aiohttp’s startup and
shutdown sequence. Note that I add the collector task to the app itself, which implements a mapping protocol so that you can use it like a dict.

I obtain our collector() coroutine off the app identifier and call cancel() on that.

Finally, you can see where the custom startup and shutdown coroutines are hooked in: the app instance provides hooks to which our custom coroutines may be appended.

## Code Explanation For charts.html

cpu and mem are each a mapping of a color to a TimeSeries() instance.

One chart instance is created for CPU, and one for memory usage.

We create a TimeSeries() instance inside the onmessage event of the
EventSource() instance. This means that any new data coming in (e.g., on a different color name) will automatically get a new time series created for it. The
add_timeseries() function creates the TimeSeries() instance and adds to the given chart instance.

Create a new EventSource() instance on the /feed URL. The browser will connect to this endpoint on our server, (collect_layer.py). Note that the browser will automatically try to reconnect if the connection is lost. Server-sent events are often overlooked, but in many situations their simplicity makes them preferable to WebSockets.

The onmessage event will fire every time the server sends data. Here the data is parsed as JSON.

Recall that the cpu identifier is a mapping of a color to a TimeSeries() instance.
Here, we obtain that time series and append data to it. We also obtain the timestamp and parse it to get the correct format required by the chart.
