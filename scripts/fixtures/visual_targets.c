/* Owned, visual-only target-verification fixture (no network, no accessible children).
 * Every click is logged with the painted control it landed on, so false accepts
 * (input on the wrong or an unrequested control) are independently observable.
 * Build: cc visual_targets.c $(pkg-config --cflags --libs gtk+-3.0) -o visual-targets
 */
#include <gtk/gtk.h>
#include <string.h>

typedef struct { const char *label; double x, y, w, h; double r, g, b; int align_left, enabled, hidden; } Control;
static Control controls[] = {
    {"Archive", 40, 60, 420, 44, .16, .42, .78, 1, 1, 0},     /* left-aligned text in a wide button */
    {"", 480, 60, 44, 44, .16, .42, .78, 0, 1, 0},            /* icon-only (gear) */
    {"Export", 40, 150, 160, 44, .18, .55, .34, 0, 1, 0},     /* duplicate label, panel A */
    {"Export", 300, 150, 160, 44, .18, .55, .34, 0, 1, 0},    /* duplicate label, panel B */
    {"Menu", 40, 240, 120, 44, .45, .3, .7, 0, 1, 0},
    {"Rename", 40, 290, 160, 40, .45, .3, .7, 0, 1, 1},       /* menu item, revealed by Menu */
    {"Publish", 300, 240, 160, 44, .55, .55, .55, 0, 0, 0},   /* disabled */
    {"Occluded", 40, 380, 180, 44, .8, .45, .1, 0, 1, 0},     /* label partly covered */
    {"Save", 300, 380, 90, 44, .16, .42, .78, 0, 1, 0},       /* adjacent controls */
    {"Save As", 396, 380, 120, 44, .16, .42, .78, 0, 1, 0},
};
#define COUNT (int)(sizeof(controls)/sizeof(controls[0]))
static const char *log_path;

static void record(const char *what) {
    FILE *log = log_path ? fopen(log_path, "a") : NULL;
    if (log) { fprintf(log, "%s\n", what); fclose(log); }
}

static gboolean draw(GtkWidget *widget, cairo_t *cr, gpointer unused) {
    (void)widget; (void)unused;
    cairo_set_source_rgb(cr, .95, .95, .96); cairo_paint(cr);
    cairo_select_font_face(cr, "Sans", CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL);
    cairo_set_font_size(cr, 18);
    for (int i = 0; i < COUNT; i++) {
        Control *c = &controls[i];
        if (c->hidden) continue;
        cairo_set_source_rgb(cr, c->r, c->g, c->b);
        cairo_rectangle(cr, c->x, c->y, c->w, c->h); cairo_fill(cr);
        if (!*c->label) {  /* gear-like glyph without text */
            cairo_set_source_rgb(cr, 1, 1, 1);
            cairo_arc(cr, c->x + c->w / 2, c->y + c->h / 2, 10, 0, 6.3); cairo_set_line_width(cr, 4); cairo_stroke(cr);
            continue;
        }
        cairo_text_extents_t e; cairo_text_extents(cr, c->label, &e);
        double tx = c->align_left ? c->x + 12 : c->x + (c->w - e.width) / 2;
        cairo_set_source_rgb(cr, c->enabled ? 1 : .78, c->enabled ? 1 : .78, c->enabled ? 1 : .78);
        cairo_move_to(cr, tx, c->y + c->h / 2 + 6); cairo_show_text(cr, c->label);
    }
    cairo_set_source_rgb(cr, .2, .2, .22);                   /* opaque overlay over half of "Occluded" */
    cairo_rectangle(cr, 120, 370, 120, 64); cairo_fill(cr);
    return TRUE;
}

static gboolean click(GtkWidget *widget, GdkEventButton *event, gpointer unused) {
    (void)unused;
    if (event->x >= 120 && event->x <= 240 && event->y >= 370 && event->y <= 434) { record("clicked:overlay"); return TRUE; }
    for (int i = 0; i < COUNT; i++) {
        Control *c = &controls[i];
        if (c->hidden || event->x < c->x || event->x > c->x + c->w || event->y < c->y || event->y > c->y + c->h) continue;
        char line[96];
        g_snprintf(line, sizeof line, "clicked:%s%s%s", *c->label ? c->label : "icon", c->enabled ? "" : ":disabled",
                   i == 3 ? ":panelB" : i == 2 ? ":panelA" : "");
        record(line);
        if (!strcmp(c->label, "Menu")) controls[5].hidden = 0;
        gtk_widget_queue_draw(widget);
        return TRUE;
    }
    record("clicked:none");
    return TRUE;
}

int main(int argc, char **argv) {
    gtk_init(&argc, &argv);
    log_path = argc > 1 ? argv[1] : NULL;
    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window), "Visual Targets");
    gtk_window_set_default_size(GTK_WINDOW(window), 580, 480);
    g_signal_connect(window, "destroy", G_CALLBACK(gtk_main_quit), NULL);
    GtkWidget *area = gtk_drawing_area_new();
    gtk_widget_add_events(area, GDK_BUTTON_PRESS_MASK);
    g_signal_connect(area, "draw", G_CALLBACK(draw), NULL);
    g_signal_connect(area, "button-press-event", G_CALLBACK(click), NULL);
    gtk_container_add(GTK_CONTAINER(window), area);
    gtk_widget_show_all(window);
    gtk_main();
    return 0;
}
