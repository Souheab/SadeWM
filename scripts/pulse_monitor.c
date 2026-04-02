/*
 * pulse_monitor — PulseAudio state monitor and control utility
 *
 * Usage:
 *   pulse_monitor monitor                             stream full-state JSON lines
 *   pulse_monitor snapshot                            print one JSON line, exit
 *   pulse_monitor set-sink-volume      <idx> <0-1>
 *   pulse_monitor set-source-volume    <idx> <0-1>
 *   pulse_monitor set-default-sink     <name>
 *   pulse_monitor set-default-source   <name>
 *   pulse_monitor move-sink-input      <stream_idx> <sink_idx>
 *   pulse_monitor set-sink-input-volume <stream_idx> <0-1>
 *   pulse_monitor set-sink-mute        <idx> 0|1
 *   pulse_monitor set-source-mute      <idx> 0|1
 *   pulse_monitor set-sink-input-mute  <idx> 0|1
 *
 * Build: gcc -O2 -Wall -o pulse_monitor pulse_monitor.c $(pkg-config --cflags --libs libpulse)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pulse/pulseaudio.h>

#define MAX_ITEMS 64
#define BUFSIZE   512

/* ── Data structures ─────────────────────────────────────────── */

typedef struct {
    uint32_t index;
    char     name[BUFSIZE];
    char     desc[BUFSIZE];
    double   vol;
    int      muted;
} Sink;

typedef struct {
    uint32_t index;
    char     name[BUFSIZE];
    char     desc[BUFSIZE];
    double   vol;
    int      muted;
} Source;

typedef struct {
    uint32_t index;
    char     name[BUFSIZE];
    uint32_t sink_index;
    double   vol;
    int      muted;
} SinkInput;

typedef enum {
    MODE_MONITOR = 0,
    MODE_SNAPSHOT,
    MODE_SET_SINK_VOL,
    MODE_SET_SOURCE_VOL,
    MODE_SET_DEFAULT_SINK,
    MODE_SET_DEFAULT_SOURCE,
    MODE_MOVE_SINK_INPUT,
    MODE_SET_SINK_INPUT_VOL,
    MODE_SET_SINK_MUTE,
    MODE_SET_SOURCE_MUTE,
    MODE_SET_SINK_INPUT_MUTE,
} Mode;

typedef struct {
    pa_mainloop *ml;
    pa_context  *ctx;

    /* Monitor / snapshot state */
    Sink        sinks[MAX_ITEMS];       int n_sinks;
    Source      sources[MAX_ITEMS];     int n_sources;
    SinkInput   sink_inputs[MAX_ITEMS]; int n_sink_inputs;
    char        default_sink[BUFSIZE];
    char        default_source[BUFSIZE];
    int         pending;
    int         refetching;
    int         dirty;

    /* Command parameters */
    Mode        mode;
    uint32_t    cmd_index;
    uint32_t    cmd_index2;
    double      cmd_vol;
    int         cmd_mute;
    char        cmd_name[BUFSIZE];
} State;

/* ── JSON helpers ────────────────────────────────────────────── */

static void json_str(const char *s) {
    putchar('"');
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') { putchar('\\'); putchar(c); }
        else if (c == '\n') fputs("\\n",  stdout);
        else if (c == '\r') fputs("\\r",  stdout);
        else if (c == '\t') fputs("\\t",  stdout);
        else if (c < 0x20)  printf("\\u%04x", (unsigned)c);
        else putchar(c);
    }
    putchar('"');
}

/* ── Forward declarations ────────────────────────────────────── */

static void check_done(State *s);
static void start_refetch(State *s);

/* ── Print JSON state ────────────────────────────────────────── */

static void print_state(State *s) {
    fputs("{\"event\":\"state\",\"default_sink\":", stdout);
    json_str(s->default_sink);
    fputs(",\"default_source\":", stdout);
    json_str(s->default_source);

    fputs(",\"sinks\":[", stdout);
    for (int i = 0; i < s->n_sinks; i++) {
        if (i) putchar(',');
        printf("{\"index\":%u,\"name\":", s->sinks[i].index);
        json_str(s->sinks[i].name);
        fputs(",\"description\":", stdout);
        json_str(s->sinks[i].desc);
        printf(",\"volume\":%.4f,\"muted\":%s}",
               s->sinks[i].vol, s->sinks[i].muted ? "true" : "false");
    }

    fputs("],\"sources\":[", stdout);
    for (int i = 0; i < s->n_sources; i++) {
        if (i) putchar(',');
        printf("{\"index\":%u,\"name\":", s->sources[i].index);
        json_str(s->sources[i].name);
        fputs(",\"description\":", stdout);
        json_str(s->sources[i].desc);
        printf(",\"volume\":%.4f,\"muted\":%s}",
               s->sources[i].vol, s->sources[i].muted ? "true" : "false");
    }

    fputs("],\"sink_inputs\":[", stdout);
    for (int i = 0; i < s->n_sink_inputs; i++) {
        if (i) putchar(',');
        printf("{\"index\":%u,\"name\":", s->sink_inputs[i].index);
        json_str(s->sink_inputs[i].name);
        printf(",\"sink_index\":%u,\"volume\":%.4f,\"muted\":%s}",
               s->sink_inputs[i].sink_index,
               s->sink_inputs[i].vol,
               s->sink_inputs[i].muted ? "true" : "false");
    }

    fputs("]}\n", stdout);
    fflush(stdout);
}

/* ── Async callbacks for monitor / snapshot ─────────────────── */

static void server_cb(pa_context *c, const pa_server_info *i, void *u) {
    State *s = u; (void)c;
    if (i) {
        strncpy(s->default_sink,   i->default_sink_name,   BUFSIZE - 1);
        strncpy(s->default_source, i->default_source_name, BUFSIZE - 1);
        s->default_sink[BUFSIZE - 1]   = '\0';
        s->default_source[BUFSIZE - 1] = '\0';
    }
    s->pending--;
    check_done(s);
}

static void sink_cb(pa_context *c, const pa_sink_info *i, int eol, void *u) {
    State *s = u; (void)c;
    if (eol > 0) { s->pending--; check_done(s); return; }
    if (!i || s->n_sinks >= MAX_ITEMS) return;
    Sink *sk = &s->sinks[s->n_sinks++];
    sk->index = i->index;
    strncpy(sk->name, i->name,        BUFSIZE - 1); sk->name[BUFSIZE - 1] = '\0';
    strncpy(sk->desc, i->description, BUFSIZE - 1); sk->desc[BUFSIZE - 1] = '\0';
    sk->vol   = (double)pa_cvolume_avg(&i->volume) / PA_VOLUME_NORM;
    sk->muted = i->mute;
}

static void source_cb(pa_context *c, const pa_source_info *i, int eol, void *u) {
    State *s = u; (void)c;
    if (eol > 0) { s->pending--; check_done(s); return; }
    if (!i || i->monitor_of_sink != PA_INVALID_INDEX) return; /* skip monitor sources */
    if (s->n_sources >= MAX_ITEMS) return;
    Source *src = &s->sources[s->n_sources++];
    src->index = i->index;
    strncpy(src->name, i->name,        BUFSIZE - 1); src->name[BUFSIZE - 1] = '\0';
    strncpy(src->desc, i->description, BUFSIZE - 1); src->desc[BUFSIZE - 1] = '\0';
    src->vol   = (double)pa_cvolume_avg(&i->volume) / PA_VOLUME_NORM;
    src->muted = i->mute;
}

static void sinput_cb(pa_context *c, const pa_sink_input_info *i, int eol, void *u) {
    State *s = u; (void)c;
    if (eol > 0) { s->pending--; check_done(s); return; }
    if (!i || s->n_sink_inputs >= MAX_ITEMS) return;
    SinkInput *si = &s->sink_inputs[s->n_sink_inputs++];
    si->index = i->index;
    const char *app = pa_proplist_gets(i->proplist, "application.name");
    if (!app || !*app) app = pa_proplist_gets(i->proplist, "media.name");
    if (!app || !*app) app = i->name;
    strncpy(si->name, app ? app : "", BUFSIZE - 1); si->name[BUFSIZE - 1] = '\0';
    si->sink_index = i->sink;
    si->vol   = (double)pa_cvolume_avg(&i->volume) / PA_VOLUME_NORM;
    si->muted = i->mute;
}

static void start_refetch(State *s) {
    s->refetching = 1;
    s->n_sinks = s->n_sources = s->n_sink_inputs = 0;
    s->default_sink[0] = s->default_source[0] = '\0';
    s->pending = 4;
    pa_context_get_server_info(s->ctx, server_cb, s);
    pa_context_get_sink_info_list(s->ctx, sink_cb, s);
    pa_context_get_source_info_list(s->ctx, source_cb, s);
    pa_context_get_sink_input_info_list(s->ctx, sinput_cb, s);
}

static void check_done(State *s) {
    if (s->pending > 0) return;
    print_state(s);
    if (s->mode == MODE_SNAPSHOT) {
        pa_mainloop_quit(s->ml, 0);
        return;
    }
    /* MODE_MONITOR: reschedule if events arrived while fetching */
    if (s->dirty) {
        s->dirty = 0;
        start_refetch(s);
    } else {
        s->refetching = 0;
    }
}

static void subscribe_cb(pa_context *c, pa_subscription_event_type_t t, uint32_t idx, void *u) {
    State *s = u; (void)c; (void)t; (void)idx;
    if (s->refetching) s->dirty = 1;
    else               start_refetch(s);
}

/* ── Command operation callback ─────────────────────────────── */

static void cmd_done_cb(pa_context *c, int success, void *u) {
    State *s = u; (void)c;
    pa_mainloop_quit(s->ml, success ? 0 : 1);
}

/* ── Context state callback ──────────────────────────────────── */

static void ctx_state_cb(pa_context *c, void *u) {
    State *s = u;
    switch (pa_context_get_state(c)) {
        case PA_CONTEXT_READY: {
            if (s->mode == MODE_MONITOR || s->mode == MODE_SNAPSHOT) {
                if (s->mode == MODE_MONITOR) {
                    pa_context_set_subscribe_callback(c, subscribe_cb, s);
                    pa_context_subscribe(c,
                        PA_SUBSCRIPTION_MASK_SINK       |
                        PA_SUBSCRIPTION_MASK_SOURCE     |
                        PA_SUBSCRIPTION_MASK_SINK_INPUT |
                        PA_SUBSCRIPTION_MASK_SERVER,
                        NULL, NULL);
                }
                start_refetch(s);
            } else {
                pa_cvolume cv;
                pa_volume_t v;
                switch (s->mode) {
                    case MODE_SET_SINK_VOL:
                        v = (pa_volume_t)(s->cmd_vol * PA_VOLUME_NORM);
                        pa_cvolume_set(&cv, 2, v);
                        pa_context_set_sink_volume_by_index(c, s->cmd_index, &cv, cmd_done_cb, s);
                        break;
                    case MODE_SET_SOURCE_VOL:
                        v = (pa_volume_t)(s->cmd_vol * PA_VOLUME_NORM);
                        pa_cvolume_set(&cv, 2, v);
                        pa_context_set_source_volume_by_index(c, s->cmd_index, &cv, cmd_done_cb, s);
                        break;
                    case MODE_SET_DEFAULT_SINK:
                        pa_context_set_default_sink(c, s->cmd_name, cmd_done_cb, s);
                        break;
                    case MODE_SET_DEFAULT_SOURCE:
                        pa_context_set_default_source(c, s->cmd_name, cmd_done_cb, s);
                        break;
                    case MODE_MOVE_SINK_INPUT:
                        pa_context_move_sink_input_by_index(c, s->cmd_index, s->cmd_index2, cmd_done_cb, s);
                        break;
                    case MODE_SET_SINK_INPUT_VOL:
                        v = (pa_volume_t)(s->cmd_vol * PA_VOLUME_NORM);
                        pa_cvolume_set(&cv, 2, v);
                        pa_context_set_sink_input_volume(c, s->cmd_index, &cv, cmd_done_cb, s);
                        break;
                    case MODE_SET_SINK_MUTE:
                        pa_context_set_sink_mute_by_index(c, s->cmd_index, s->cmd_mute, cmd_done_cb, s);
                        break;
                    case MODE_SET_SOURCE_MUTE:
                        pa_context_set_source_mute_by_index(c, s->cmd_index, s->cmd_mute, cmd_done_cb, s);
                        break;
                    case MODE_SET_SINK_INPUT_MUTE:
                        pa_context_set_sink_input_mute(c, s->cmd_index, s->cmd_mute, cmd_done_cb, s);
                        break;
                    default:
                        pa_mainloop_quit(s->ml, 1);
                        break;
                }
            }
            break;
        }
        case PA_CONTEXT_FAILED:
        case PA_CONTEXT_TERMINATED:
            fprintf(stderr, "pulse_monitor: PA connection failed\n");
            pa_mainloop_quit(s->ml, 1);
            break;
        default:
            break;
    }
}

/* ── main ───────────────────────────────────────────────────── */

static void print_usage(void) {
    fputs(
        "Usage:\n"
        "  pulse_monitor monitor\n"
        "  pulse_monitor snapshot\n"
        "  pulse_monitor set-sink-volume       <index> <0.0-1.0>\n"
        "  pulse_monitor set-source-volume     <index> <0.0-1.0>\n"
        "  pulse_monitor set-default-sink      <name>\n"
        "  pulse_monitor set-default-source    <name>\n"
        "  pulse_monitor move-sink-input       <stream_index> <sink_index>\n"
        "  pulse_monitor set-sink-input-volume <stream_index> <0.0-1.0>\n"
        "  pulse_monitor set-sink-mute         <index> <0|1>\n"
        "  pulse_monitor set-source-mute       <index> <0|1>\n"
        "  pulse_monitor set-sink-input-mute   <index> <0|1>\n",
        stderr);
}

int main(int argc, char *argv[]) {
    if (argc < 2) { print_usage(); return 1; }

    State s;
    memset(&s, 0, sizeof s);

    const char *cmd = argv[1];

    if (strcmp(cmd, "monitor") == 0) {
        s.mode = MODE_MONITOR;
    } else if (strcmp(cmd, "snapshot") == 0) {
        s.mode = MODE_SNAPSHOT;
    } else if (strcmp(cmd, "set-sink-volume") == 0 && argc >= 4) {
        s.mode = MODE_SET_SINK_VOL;
        s.cmd_index = (uint32_t)atoi(argv[2]);
        s.cmd_vol   = atof(argv[3]);
    } else if (strcmp(cmd, "set-source-volume") == 0 && argc >= 4) {
        s.mode = MODE_SET_SOURCE_VOL;
        s.cmd_index = (uint32_t)atoi(argv[2]);
        s.cmd_vol   = atof(argv[3]);
    } else if (strcmp(cmd, "set-default-sink") == 0 && argc >= 3) {
        s.mode = MODE_SET_DEFAULT_SINK;
        strncpy(s.cmd_name, argv[2], BUFSIZE - 1);
    } else if (strcmp(cmd, "set-default-source") == 0 && argc >= 3) {
        s.mode = MODE_SET_DEFAULT_SOURCE;
        strncpy(s.cmd_name, argv[2], BUFSIZE - 1);
    } else if (strcmp(cmd, "move-sink-input") == 0 && argc >= 4) {
        s.mode      = MODE_MOVE_SINK_INPUT;
        s.cmd_index  = (uint32_t)atoi(argv[2]);
        s.cmd_index2 = (uint32_t)atoi(argv[3]);
    } else if (strcmp(cmd, "set-sink-input-volume") == 0 && argc >= 4) {
        s.mode      = MODE_SET_SINK_INPUT_VOL;
        s.cmd_index = (uint32_t)atoi(argv[2]);
        s.cmd_vol   = atof(argv[3]);
    } else if (strcmp(cmd, "set-sink-mute") == 0 && argc >= 4) {
        s.mode      = MODE_SET_SINK_MUTE;
        s.cmd_index = (uint32_t)atoi(argv[2]);
        s.cmd_mute  = atoi(argv[3]);
    } else if (strcmp(cmd, "set-source-mute") == 0 && argc >= 4) {
        s.mode      = MODE_SET_SOURCE_MUTE;
        s.cmd_index = (uint32_t)atoi(argv[2]);
        s.cmd_mute  = atoi(argv[3]);
    } else if (strcmp(cmd, "set-sink-input-mute") == 0 && argc >= 4) {
        s.mode      = MODE_SET_SINK_INPUT_MUTE;
        s.cmd_index = (uint32_t)atoi(argv[2]);
        s.cmd_mute  = atoi(argv[3]);
    } else {
        print_usage();
        return 1;
    }

    s.ml  = pa_mainloop_new();
    pa_mainloop_api *api = pa_mainloop_get_api(s.ml);
    s.ctx = pa_context_new(api, "pulse_monitor");
    pa_context_set_state_callback(s.ctx, ctx_state_cb, &s);

    if (pa_context_connect(s.ctx, NULL, 0, NULL) < 0) {
        fprintf(stderr, "pulse_monitor: pa_context_connect failed\n");
        pa_context_unref(s.ctx);
        pa_mainloop_free(s.ml);
        return 1;
    }

    int exit_code = 0;
    pa_mainloop_run(s.ml, &exit_code);
    pa_context_unref(s.ctx);
    pa_mainloop_free(s.ml);
    return exit_code;
}
