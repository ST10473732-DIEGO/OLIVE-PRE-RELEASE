/* Owned, local-only, visual-only messaging fixture. No network, tokens or real client.
 * Everything is painted on one GtkDrawingArea, so AT-SPI exposes no controls and the
 * visual messaging route must ground, verify and act from frames alone.
 * Conventions mirror a common chat layout: server header, channel list, account panel,
 * composer placeholder "Message #channel", Ctrl+K quick switcher and Enter to send.
 * Every accepted send is appended to the owned log given as argv[1] for exactly-once checks.
 * Build: cc visual_messenger.c $(pkg-config --cflags --libs gtk+-3.0) -o visual-messenger
 */
#include <gtk/gtk.h>
#include <string.h>

typedef struct { const char *server; const char *channel; } Channel;
static const Channel CHANNELS[] = {
    {"Osprey Workshop", "general"}, {"Osprey Workshop", "releases"},
    {"Heron Lab", "general"}, {"Heron Lab", "field-notes"}, {"Heron Lab", "releases"},
};
#define COUNT (int)(sizeof(CHANNELS)/sizeof(CHANNELS[0]))
static int current = 0, focus_composer = 0, switcher = 0;
static GString *drafts[COUNT], *query;
static GPtrArray *messages[COUNT];
static const char *log_path;
static GtkWidget *area;
static int matches[COUNT], match_count;

static void text(cairo_t *cr, double x, double y, double size, double grey, const char *value) {
    cairo_select_font_face(cr, "Sans", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
    cairo_set_font_size(cr, size);
    cairo_set_source_rgb(cr, grey, grey, grey);
    cairo_move_to(cr, x, y);
    cairo_show_text(cr, value);
}

static void rect(cairo_t *cr, double x, double y, double w, double h, double r, double g, double b) {
    cairo_set_source_rgb(cr, r, g, b);
    cairo_rectangle(cr, x, y, w, h);
    cairo_fill(cr);
}

static void filter(void) {
    match_count = 0;
    for (int i = 0; i < COUNT; i++)
        if (!query->len || strstr(CHANNELS[i].channel, query->str)) matches[match_count++] = i;
}

static gboolean draw(GtkWidget *widget, cairo_t *cr, gpointer unused) {
    (void)unused;
    int w = gtk_widget_get_allocated_width(widget), h = gtk_widget_get_allocated_height(widget);
    rect(cr, 0, 0, w, h, .19, .2, .22);
    rect(cr, 0, 0, 72, h, .12, .12, .13);
    rect(cr, 72, 0, 240, h, .17, .18, .19);
    text(cr, 20, 44, 16, .9, "OW");
    text(cr, 22, 104, 16, .9, "HL");
    const char *server = CHANNELS[current].server;
    text(cr, 88, 34, 17, .95, server);
    int row = 0;
    for (int i = 0; i < COUNT; i++) {
        if (strcmp(CHANNELS[i].server, server)) continue;
        char label[96];
        g_snprintf(label, sizeof label, "# %s", CHANNELS[i].channel);
        if (i == current) rect(cr, 80, 64 + row * 36, 224, 30, .25, .26, .28);
        text(cr, 92, 85 + row * 36, 16, i == current ? .95 : .7, label);
        row++;
    }
    rect(cr, 72, h - 52, 240, 52, .14, .14, .16);
    text(cr, 88, h - 20, 15, .9, "fixture-owner");
    char header[96];
    g_snprintf(header, sizeof header, "# %s", CHANNELS[current].channel);
    text(cr, 332, 34, 17, .95, header);
    rect(cr, 312, 52, w - 312, 1, .3, .3, .32);
    GPtrArray *list = messages[current];
    for (guint i = 0; i < list->len; i++) {
        double y = h - 110 - (list->len - 1 - i) * 48;
        if (y < 70) continue;
        text(cr, 332, y - 18, 13, .6, "fixture-owner");
        text(cr, 332, y, 16, .92, g_ptr_array_index(list, i));
        text(cr, w - 70, y, 12, .55, "Sent");
    }
    rect(cr, 328, h - 66, w - 348, 46, .22, .23, .26);
    if (drafts[current]->len) {
        text(cr, 344, h - 36, 16, .95, drafts[current]->str);
    } else {
        char placeholder[112];
        g_snprintf(placeholder, sizeof placeholder, "Message #%s", CHANNELS[current].channel);
        text(cr, 344, h - 36, 16, .62, placeholder);
    }
    if (focus_composer && !switcher) rect(cr, 328, h - 22, w - 348, 2, .35, .5, .95);
    if (switcher) {
        double x = w / 2.0 - 260, y = 120;
        rect(cr, 0, 0, w, h, .05, .05, .06);
        rect(cr, x, y, 520, 90 + match_count * 40, .2, .21, .24);
        rect(cr, x + 20, y + 20, 480, 44, .12, .12, .14);
        text(cr, x + 34, y + 49, 17, query->len ? .95 : .62, query->len ? query->str : "Where would you like to go?");
        for (int i = 0; i < match_count; i++) {
            char label[96];
            g_snprintf(label, sizeof label, "# %s", CHANNELS[matches[i]].channel);
            text(cr, x + 34, y + 104 + i * 40, 16, .92, label);
            text(cr, x + 300, y + 104 + i * 40, 14, .66, CHANNELS[matches[i]].server);
        }
    }
    return TRUE;
}

static void record(const char *value) {
    FILE *file = fopen(log_path, "a");
    if (!file) return;
    fprintf(file, "%s\t%s\t%s\n", CHANNELS[current].server, CHANNELS[current].channel, value);
    fclose(file);
}

static gboolean click(GtkWidget *widget, GdkEventButton *event, gpointer unused) {
    (void)unused;
    int w = gtk_widget_get_allocated_width(widget), h = gtk_widget_get_allocated_height(widget);
    gtk_widget_grab_focus(widget);
    if (switcher) {
        double x = w / 2.0 - 260, y = 120;
        for (int i = 0; i < match_count; i++) {
            double top = y + 104 + i * 40 - 22;
            if (event->x >= x + 20 && event->x <= x + 500 && event->y >= top && event->y <= top + 34) {
                current = matches[i];
                switcher = 0;
                focus_composer = 1;
            }
        }
    } else if (event->x > 312 && event->y > h - 70) {
        focus_composer = 1;
    } else if (event->x > 72 && event->x < 312 && event->y > 60 && event->y < h - 60) {
        int row = (int)((event->y - 64) / 36), seen = 0;
        for (int i = 0; i < COUNT; i++) {
            if (strcmp(CHANNELS[i].server, CHANNELS[current].server)) continue;
            if (seen++ == row) { current = i; break; }
        }
        focus_composer = 0;
    } else if (event->x < 72) {
        const char *server = event->y < 72 ? "Osprey Workshop" : event->y < 132 ? "Heron Lab" : NULL;
        for (int i = 0; server && i < COUNT; i++)
            if (!strcmp(CHANNELS[i].server, server)) { current = i; break; }
        focus_composer = 0;
    } else {
        focus_composer = 0;
    }
    gtk_widget_queue_draw(widget);
    return TRUE;
}

static gboolean key(GtkWidget *widget, GdkEventKey *event, gpointer unused) {
    (void)unused;
    guint value = event->keyval;
    if ((event->state & GDK_CONTROL_MASK) && (value == GDK_KEY_k || value == GDK_KEY_K)) {
        switcher = 1; g_string_truncate(query, 0); filter();
    } else if (switcher) {
        if (value == GDK_KEY_Escape) switcher = 0;
        else if (value == GDK_KEY_BackSpace && query->len) g_string_truncate(query, query->len - 1);
        else if (value == GDK_KEY_Return && match_count == 1) { current = matches[0]; switcher = 0; focus_composer = 1; }
        else if (gdk_keyval_to_unicode(value) >= 32) g_string_append_unichar(query, gdk_keyval_to_unicode(value));
        filter();
    } else if (focus_composer) {
        GString *draft = drafts[current];
        if (value == GDK_KEY_Return && !(event->state & GDK_SHIFT_MASK)) {
            if (draft->len) {
                g_ptr_array_add(messages[current], g_strdup(draft->str));
                record(draft->str);
                g_string_truncate(draft, 0);
            }
        } else if (value == GDK_KEY_BackSpace && draft->len) {
            g_string_truncate(draft, draft->len - 1);
        } else if (gdk_keyval_to_unicode(value) >= 32) {
            g_string_append_unichar(draft, gdk_keyval_to_unicode(value));
        }
    }
    gtk_widget_queue_draw(widget);
    return TRUE;
}

int main(int argc, char **argv) {
    gtk_init(&argc, &argv);
    log_path = argc > 1 ? argv[1] : "visual-messenger-sent.log";
    query = g_string_new("");
    for (int i = 0; i < COUNT; i++) { drafts[i] = g_string_new(""); messages[i] = g_ptr_array_new_with_free_func(g_free); }
    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window), "Visual Messenger");
    gtk_window_set_default_size(GTK_WINDOW(window), 1000, 680);
    g_signal_connect(window, "destroy", G_CALLBACK(gtk_main_quit), NULL);
    area = gtk_drawing_area_new();
    gtk_widget_set_can_focus(area, TRUE);
    gtk_widget_add_events(area, GDK_BUTTON_PRESS_MASK | GDK_KEY_PRESS_MASK);
    g_signal_connect(area, "draw", G_CALLBACK(draw), NULL);
    g_signal_connect(area, "button-press-event", G_CALLBACK(click), NULL);
    g_signal_connect(area, "key-press-event", G_CALLBACK(key), NULL);
    gtk_container_add(GTK_CONTAINER(window), area);
    gtk_widget_show_all(window);
    gtk_widget_grab_focus(area);
    gtk_main();
    return 0;
}
