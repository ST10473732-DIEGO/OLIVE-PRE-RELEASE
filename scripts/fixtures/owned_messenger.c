/* Owned local-only GUI acceptance fixture. No network, tokens or external client.
 * Build: cc owned_messenger.c $(pkg-config --cflags --libs gtk+-3.0) -o owned-messenger
 */
#include <gtk/gtk.h>
static GtkWidget *composer, *heading, *messages;
static gboolean sample_ready=FALSE;
static gboolean draw_sample(GtkWidget *area, cairo_t *cr, gpointer unused) {
    (void)unused;
    int width=gtk_widget_get_allocated_width(area);
    cairo_set_source_rgb(cr,sample_ready?0.1:0.15,0.35,0.55);cairo_paint(cr);
    cairo_select_font_face(cr,"Sans",CAIRO_FONT_SLANT_NORMAL,CAIRO_FONT_WEIGHT_NORMAL);
    cairo_set_font_size(cr,28);
    const char *label=sample_ready?"Sample ready":"New sample";
    cairo_text_extents_t ext;cairo_text_extents(cr,label,&ext);
    cairo_move_to(cr,(width-ext.width)/2,47);cairo_set_source_rgb(cr,1,1,1);cairo_show_text(cr,label);
    return TRUE;
}
static gboolean click_sample(GtkWidget *area, GdkEventButton *event, gpointer unused) {
    (void)event;(void)unused;sample_ready=TRUE;gtk_widget_queue_draw(area);return TRUE;
}
static void name(GtkWidget *widget, const char *value) {
    atk_object_set_name(gtk_widget_get_accessible(widget), value);
}
static void channel(GtkButton *button, gpointer unused) {
    (void)unused;
    /* Preserve unrelated drafts; switching refuses a nonempty composer. */
    if (*gtk_entry_get_text(GTK_ENTRY(composer))) return;
    gtk_label_set_text(GTK_LABEL(heading), gtk_button_get_label(button));
}
static void send_message(GtkButton *button, gpointer unused) {
    (void)button; (void)unused;
    const char *text = gtk_entry_get_text(GTK_ENTRY(composer));
    if (!*text) return;
    GtkWidget *row=gtk_list_box_row_new(), *box=gtk_box_new(GTK_ORIENTATION_VERTICAL,4);
    name(row,"Outgoing message");
    gtk_container_add(GTK_CONTAINER(row),box);
    gtk_box_pack_start(GTK_BOX(box),gtk_label_new(text),FALSE,FALSE,0);
    gtk_box_pack_start(GTK_BOX(box),gtk_label_new("Delivered"),FALSE,FALSE,0);
    gtk_list_box_insert(GTK_LIST_BOX(messages),row,-1);
    gtk_widget_show_all(row);
    gtk_entry_set_text(GTK_ENTRY(composer),"");
}
static void resize_window(GtkButton *button, gpointer window) {
    (void)button;
    gtk_window_resize(GTK_WINDOW(window),720,540);
}
int main(int argc, char **argv) {
    gtk_init(&argc,&argv);
    GtkWidget *window=gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window),"OLIVE owned messenger");
    gtk_window_set_default_size(GTK_WINDOW(window),800,600);
    g_signal_connect(window,"destroy",G_CALLBACK(gtk_main_quit),NULL);
    GtkWidget *box=gtk_box_new(GTK_ORIENTATION_VERTICAL,12);
    gtk_container_set_border_width(GTK_CONTAINER(box),20);
    gtk_container_add(GTK_CONTAINER(window),box);
    gtk_box_pack_start(GTK_BOX(box),gtk_label_new("Account: Fixture owner"),FALSE,FALSE,0);
    GtkWidget *resize=gtk_button_new_with_label("Resize window");
    g_signal_connect(resize,"clicked",G_CALLBACK(resize_window),window);
    gtk_box_pack_start(GTK_BOX(box),resize,FALSE,FALSE,0);
    GtkWidget *tabs=gtk_notebook_new();
    const char *servers[]={"Cedar Lab","Osprey Workshop"};
    const char *channels[]={"planning","garden","release notes","ideas"};
    for(int i=0;i<2;i++) {
        GtkWidget *page=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,12);
        for(int j=0;j<2;j++) {
            GtkWidget *button=gtk_button_new_with_label(channels[i*2+j]);
            g_signal_connect(button,"clicked",G_CALLBACK(channel),NULL);
            gtk_box_pack_start(GTK_BOX(page),button,TRUE,TRUE,0);
        }
        gtk_notebook_append_page(GTK_NOTEBOOK(tabs),page,gtk_label_new(servers[i]));
    }
    gtk_box_pack_start(GTK_BOX(box),tabs,FALSE,FALSE,0);
    heading=gtk_label_new("planning");
    atk_object_set_role(gtk_widget_get_accessible(heading),ATK_ROLE_HEADING);
    gtk_box_pack_start(GTK_BOX(box),heading,FALSE,FALSE,0);
    GtkWidget *area=gtk_drawing_area_new();
    gtk_widget_set_size_request(area,-1,75);
    gtk_widget_add_events(area,GDK_BUTTON_PRESS_MASK);
    g_signal_connect(area,"draw",G_CALLBACK(draw_sample),NULL);
    g_signal_connect(area,"button-press-event",G_CALLBACK(click_sample),NULL);
    gtk_box_pack_start(GTK_BOX(box),area,FALSE,FALSE,0);
    messages=gtk_list_box_new();
    gtk_box_pack_start(GTK_BOX(box),messages,TRUE,TRUE,0);
    composer=gtk_entry_new();name(composer,"Message");
    gtk_box_pack_start(GTK_BOX(box),composer,FALSE,FALSE,0);
    GtkWidget *send=gtk_button_new_with_label("Send");
    g_signal_connect(send,"clicked",G_CALLBACK(send_message),NULL);
    gtk_box_pack_start(GTK_BOX(box),send,FALSE,FALSE,0);
    gtk_widget_show_all(window);gtk_main();return 0;
}
