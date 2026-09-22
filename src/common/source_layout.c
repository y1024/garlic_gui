#include "source_layout.h"
#include "types.h"
#include "file_tools.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct LayoutEntry {
    char *key;
    char *value;
    struct LayoutEntry *next;
} LayoutEntry;

static LayoutEntry **buckets;
static size_t bucket_count;
static pthread_once_t load_once = PTHREAD_ONCE_INIT;

static unsigned layout_hash(const char *text) {
    unsigned hash = 2166136261u;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p)
        hash = (hash ^ *p) * 16777619u;
    return hash;
}

static char *plain_class_name(const char *name) {
    size_t len;
    if (!name) return NULL;
    len = strlen(name);
    if (len > 2 && name[0] == 'L' && name[len - 1] == ';')
        return strndup(name + 1, len - 2);
    return strdup(name);
}

static void layout_insert(char *key, char *value) {
    unsigned index;
    LayoutEntry *entry;
    if (!key || !value) {
        free(key);
        free(value);
        return;
    }
    if (bucket_count == 0) {
        bucket_count = 1024;
        buckets = calloc(bucket_count, sizeof(*buckets));
        if (!buckets) {
            bucket_count = 0;
            free(key);
            free(value);
            return;
        }
    }
    index = layout_hash(key) & (bucket_count - 1);
    for (entry = buckets[index]; entry; entry = entry->next) {
        if (strcmp(entry->key, key) == 0) {
            free(entry->value);
            entry->value = value;
            free(key);
            return;
        }
    }
    entry = calloc(1, sizeof(*entry));
    if (!entry) {
        free(key);
        free(value);
        return;
    }
    entry->key = key;
    entry->value = value;
    entry->next = buckets[index];
    buckets[index] = entry;
}

static void load_path_map(void) {
    const char *path = getenv("GARLIC_PATH_MAP");
    FILE *file;
    char line[65536];
    if (!path || !*path) return;
    file = fopen(path, "rb");
    if (!file) return;
    while (fgets(line, sizeof line, file)) {
        char *tab = strchr(line, '\t');
        char *end;
        if (!tab || tab == line) continue;
        *tab = 0;
        end = tab + 1;
        end[strcspn(end, "\r\n")] = 0;
        if (!*end) continue;
        layout_insert(strdup(line), strdup(end));
    }
    fclose(file);
}

char *source_layout_override(const char *name) {
    char *plain;
    LayoutEntry *entry;
    unsigned index;
    pthread_once(&load_once, load_path_map);
    if (!buckets || !name) return NULL;
    plain = plain_class_name(name);
    if (!plain) return NULL;
    index = layout_hash(plain) & (bucket_count - 1);
    for (entry = buckets[index]; entry; entry = entry->next) {
        if (strcmp(entry->key, plain) == 0) {
            char *value = strdup(entry->value);
            free(plain);
            return value;
        }
    }
    free(plain);
    return NULL;
}

char *source_layout_mapped_path(const char *dir, const char *class_name, const char *extension) {
    char *stem, *path, *parent, *slash;
    size_t dir_len, stem_len, ext_len;
    if (!dir || !class_name || !extension) return NULL;
    stem = source_layout_override(class_name);
    if (!stem) return NULL;
    dir_len = strlen(dir);
    stem_len = strlen(stem);
    ext_len = strlen(extension);
    path = malloc(dir_len + 1 + stem_len + ext_len + 1);
    if (!path) {
        free(stem);
        return NULL;
    }
    memcpy(path, dir, dir_len);
    path[dir_len] = '/';
    memcpy(path + dir_len + 1, stem, stem_len);
    memcpy(path + dir_len + 1 + stem_len, extension, ext_len + 1);
    free(stem);
    parent = strdup(path);
    slash = parent ? strrchr(parent, '/') : NULL;
    if (slash) {
        *slash = 0;
        make_dir(parent);
    }
    free(parent);
    return path;
}
