/* Owned, non-networked navigation/ambiguity acceptance controls.
 * cc freeform_controls.c $(pkg-config --cflags --libs gtk+-3.0) -o freeform-controls
 */
#include <gtk/gtk.h>
static GtkWidget *amber, *status;
static void reveal(GtkButton *button, gpointer data) {
    (void)data;
    gtk_widget_show(amber);
    gtk_button_set_label(button,"Menu opened");
}
static void selected(GtkButton *button, gpointer data) {
    (void)data;
    gtk_label_set_text(GTK_LABEL(status),gtk_button_get_label(button));
    g_print("activated:%s\n",gtk_button_get_label(button));
}
int main(int argc, char **argv) {
    gtk_init(&argc,&argv);
    GtkWidget *window=gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window),"OLIVE owned freeform controls");
    gtk_window_set_default_size(GTK_WINDOW(window),760,540);
    g_signal_connect(window,"destroy",G_CALLBACK(gtk_main_quit),NULL);
    GtkWidget *box=gtk_box_new(GTK_ORIENTATION_VERTICAL,12);
    gtk_container_set_border_width(GTK_CONTAINER(box),16);
    gtk_container_add(GTK_CONTAINER(window),box);
    gtk_box_pack_start(GTK_BOX(box),gtk_label_new("Account: Fixture owner"),FALSE,FALSE,0);
    GtkWidget *menu=gtk_button_new_with_label("Menu");
    g_signal_connect(menu,"clicked",G_CALLBACK(reveal),NULL);
    gtk_box_pack_start(GTK_BOX(box),menu,FALSE,FALSE,0);
    amber=gtk_button_new_with_label("Amber");
    g_signal_connect(amber,"clicked",G_CALLBACK(selected),NULL);
    gtk_box_pack_start(GTK_BOX(box),amber,FALSE,FALSE,0);
    GtkWidget *people=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,12);
    for(int i=0;i<2;i++) {
        GtkWidget *person=gtk_button_new_with_label("Robin");
        g_signal_connect(person,"clicked",G_CALLBACK(selected),NULL);
        gtk_box_pack_start(GTK_BOX(people),person,TRUE,TRUE,0);
    }
    gtk_box_pack_start(GTK_BOX(box),people,FALSE,FALSE,0);
    GtkWidget *heading=gtk_label_new("No conversation selected");
    atk_object_set_role(gtk_widget_get_accessible(heading),ATK_ROLE_HEADING);
    gtk_box_pack_start(GTK_BOX(box),heading,FALSE,FALSE,0);
    GtkWidget *scroll=gtk_scrolled_window_new(NULL,NULL);
    gtk_widget_set_size_request(scroll,-1,180);
    GtkWidget *list=gtk_box_new(GTK_ORIENTATION_VERTICAL,16);
    for(int i=0;i<12;i++) {
        GtkWidget *row=gtk_label_new("Owned navigation row");
        gtk_widget_set_size_request(row,-1,32);
        gtk_box_pack_start(GTK_BOX(list),row,FALSE,FALSE,0);
    }
    GtkWidget *cobalt=gtk_button_new_with_label("Cobalt");
    g_signal_connect(cobalt,"clicked",G_CALLBACK(selected),NULL);
    gtk_box_pack_start(GTK_BOX(list),cobalt,FALSE,FALSE,0);
    gtk_container_add(GTK_CONTAINER(scroll),list);
    gtk_box_pack_start(GTK_BOX(box),scroll,TRUE,TRUE,0);
    GtkWidget *entry=gtk_entry_new();
    atk_object_set_name(gtk_widget_get_accessible(entry),"Message");
    gtk_box_pack_start(GTK_BOX(box),entry,FALSE,FALSE,0);
    status=gtk_label_new("No activation");
    gtk_box_pack_start(GTK_BOX(box),status,FALSE,FALSE,0);
    gtk_widget_show_all(window);
    gtk_widget_hide(amber);
    gtk_main();return 0;
}
