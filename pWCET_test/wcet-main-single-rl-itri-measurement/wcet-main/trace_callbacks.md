
There are two bpfcc Python frontends that generate trace files for latter analysis:
1. `trace_et.py`: trace a single callback function
2. `trace_ets.py`: trace multiple callback functions

In both frontends, context switches associated with the callback functions are also traced,
shown as brown blocks in the following image.

![trace_ets_ui.png](image/trace_ets_ui.png)


### Usage:

For `trace_et.py`:

```
sudo python3 trace_et.py -i demangled_callback_name
```

For `trace_ets.py`:

```
sudo python3 trace_ets.py -i /path/to/callbacks.txt
```
where callbacks.txt contains demangled callback names, one for a line.

The output trace is saved in `/tmp/trace.json` by default, but can be changed with the -o option.

The [trace event format](https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/preview?tab=t.0#heading=h.yr4qxyxotyw) can be displayed in chrome tracing tab or perfetto.

### Show trace events in chrome tracing tab

1. Launch chrome browser.
2. In the URL bar, type in `chrome://tracing`.
If you see the `Internal debugging pages are currently disabled` message,
follow the link to enable it.
3. Click the `Load` button, and select /tmp/trace.json.

### Show trace events in perfetto

1. Launch chrome browser.
2. Navigate to [https://ui.perfetto.dev](https://ui.perfetto.dev)
3. Click `Open trace file` and select /tmp/trace.json.

As far as I known, trace file analysis is done on our local browser.
It won't be sent over network for further analysis.

### Reveal improper execution of callback functions

Tracing can show the improper execution of callback functions.
One callback is expected to follow another one, but sometimes it does not do so,
as the following image shows.

![improper_cb_execution.png](image/improper_cb_execution.png)
