#ifndef GARLIC_SOURCE_LAYOUT_H
#define GARLIC_SOURCE_LAYOUT_H

/* Relative export stem for names that must not use their literal path.
 * Returns a malloc'd string, or NULL when the literal package path is used. */
char *source_layout_override(const char *name);

/* dir/stem.extension for an override, with parent directories created.
 * Returns a malloc'd path, or NULL when this class keeps its literal path. */
char *source_layout_mapped_path(const char *dir, const char *class_name, const char *extension);

#endif
