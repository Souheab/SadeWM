/* configfile.c — runtime TOML config loader for sadewm.
 * Included at the bottom of sadewm.c (same translation unit) so it can
 * read and write the static variables declared there.
 */
#include "configfile.h"
#include "tomlc17.h"
#include <stdio.h>
#include <string.h>

/* Persistent storage — the char buffers inside here are what colors[] and
 * fonts[] pointers are redirected to after a successful config load. */
static FileConfig g_fileconfig;

/* String storage backing the Rule entries built from config file rules. */
static char loaded_rule_class[CONFIGFILE_MAX_RULES][64];
static char loaded_rule_instance[CONFIGFILE_MAX_RULES][64];
static char loaded_rule_title[CONFIGFILE_MAX_RULES][64];
static Rule loaded_rules[CONFIGFILE_MAX_RULES];

static void
configfile_load(const char *path, FileConfig *out)
{
	memset(out, 0, sizeof *out);

	toml_result_t res = toml_parse_file_ex(path);
	if (!res.ok)
		return; /* file absent or parse error — silent fallback to compiled defaults */

	toml_datum_t root = res.toptab;
	toml_datum_t v;

	/* [appearance] */
	v = toml_seek(root, "appearance.borderpx");
	if (v.type == TOML_INT64) { out->borderpx = (unsigned int)v.u.int64; out->has_borderpx = 1; }

	v = toml_seek(root, "appearance.gappx");
	if (v.type == TOML_INT64) { out->gappx = (unsigned int)v.u.int64; out->has_gappx = 1; }

	v = toml_seek(root, "appearance.snap");
	if (v.type == TOML_INT64) { out->snap = (unsigned int)v.u.int64; out->has_snap = 1; }

	v = toml_seek(root, "appearance.font");
	if (v.type == TOML_STRING) {
		snprintf(out->font, sizeof out->font, "%s", v.u.s);
		out->has_font = 1;
	}

	/* [colors.norm] and [colors.sel] */
	{
		static const char *scheme_keys[2] = { "colors.norm", "colors.sel" };
		static const char *slot_keys[3]   = { "fg", "bg", "border" };
		int s, slot;
		for (s = 0; s < 2; s++) {
			toml_datum_t scheme = toml_seek(root, scheme_keys[s]);
			if (scheme.type != TOML_TABLE) continue;
			for (slot = 0; slot < 3; slot++) {
				v = toml_get(scheme, slot_keys[slot]);
				if (v.type == TOML_STRING) {
					snprintf(out->colors[s][slot],
					         sizeof out->colors[s][slot], "%s", v.u.s);
					out->has_colors[s][slot] = 1;
				}
			}
		}
	}

	/* [layout] */
	v = toml_seek(root, "layout.mfact");
	if      (v.type == TOML_FP64)  { out->mfact = (float)v.u.fp64;  out->has_mfact = 1; }
	else if (v.type == TOML_INT64) { out->mfact = (float)v.u.int64; out->has_mfact = 1; }

	v = toml_seek(root, "layout.nmaster");
	if (v.type == TOML_INT64) { out->nmaster = (int)v.u.int64; out->has_nmaster = 1; }

	v = toml_seek(root, "layout.topoffset");
	if (v.type == TOML_INT64) { out->topoffset = (unsigned int)v.u.int64; out->has_topoffset = 1; }

	v = toml_seek(root, "layout.bottomoffset");
	if (v.type == TOML_INT64) { out->bottomoffset = (unsigned int)v.u.int64; out->has_bottomoffset = 1; }

	v = toml_seek(root, "layout.resizehints");
	if      (v.type == TOML_BOOLEAN) { out->resizehints = v.u.boolean ? 1 : 0; out->has_resizehints = 1; }
	else if (v.type == TOML_INT64)   { out->resizehints = (int)v.u.int64;       out->has_resizehints = 1; }

	v = toml_seek(root, "layout.lockfullscreen");
	if      (v.type == TOML_BOOLEAN) { out->lockfullscreen = v.u.boolean ? 1 : 0; out->has_lockfullscreen = 1; }
	else if (v.type == TOML_INT64)   { out->lockfullscreen = (int)v.u.int64;       out->has_lockfullscreen = 1; }

	/* [[rules]] */
	{
		toml_datum_t rules_arr = toml_get(root, "rules");
		if (rules_arr.type == TOML_ARRAY) {
			int n = rules_arr.u.arr.size;
			int i;
			if (n > CONFIGFILE_MAX_RULES) n = CONFIGFILE_MAX_RULES;
			out->has_rules = 1;
			out->nrules    = n;
			for (i = 0; i < n; i++) {
				toml_datum_t entry = rules_arr.u.arr.elem[i];
				FileRule *r = &out->rules[i];
				if (entry.type != TOML_TABLE) continue;

				r->monitor = -1; /* default: any monitor */

				v = toml_get(entry, "class");
				if (v.type == TOML_STRING)
					snprintf(r->class, sizeof r->class, "%s", v.u.s);

				v = toml_get(entry, "instance");
				if (v.type == TOML_STRING)
					snprintf(r->instance, sizeof r->instance, "%s", v.u.s);

				v = toml_get(entry, "title");
				if (v.type == TOML_STRING)
					snprintf(r->title, sizeof r->title, "%s", v.u.s);

				v = toml_get(entry, "tags_mask");
				if (v.type == TOML_INT64)
					r->tags = (unsigned int)v.u.int64;

				v = toml_get(entry, "isfloating");
				if      (v.type == TOML_BOOLEAN) r->isfloating = v.u.boolean ? 1 : 0;
				else if (v.type == TOML_INT64)   r->isfloating = (int)v.u.int64;

				v = toml_get(entry, "monitor");
				if (v.type == TOML_INT64) r->monitor = (int)v.u.int64;
			}
		}
	}

	toml_free(res);
}

static void
applyconfigfile(const FileConfig *fc)
{
	if (fc->has_borderpx)     borderpx      = fc->borderpx;
	if (fc->has_gappx)        gappx         = fc->gappx;
	if (fc->has_snap)         snap          = fc->snap;
	if (fc->has_font)         fonts[0]      = fc->font;

	{
		int s, slot;
		for (s = 0; s < 2; s++)
			for (slot = 0; slot < 3; slot++)
				if (fc->has_colors[s][slot])
					colors[s][slot] = fc->colors[s][slot];
	}

	if (fc->has_mfact)          mfact          = fc->mfact;
	if (fc->has_nmaster)        nmaster        = fc->nmaster;
	if (fc->has_topoffset)      topoffset      = fc->topoffset;
	if (fc->has_bottomoffset)   bottomoffset   = fc->bottomoffset;
	if (fc->has_resizehints)    resizehints    = fc->resizehints;
	if (fc->has_lockfullscreen) lockfullscreen = fc->lockfullscreen;

	if (fc->has_rules) {
		int i, n = fc->nrules;
		for (i = 0; i < n; i++) {
			const FileRule *fr = &fc->rules[i];
			loaded_rule_class[i][0]    = '\0';
			loaded_rule_instance[i][0] = '\0';
			loaded_rule_title[i][0]    = '\0';
			if (fr->class[0])    snprintf(loaded_rule_class[i],    64, "%s", fr->class);
			if (fr->instance[0]) snprintf(loaded_rule_instance[i], 64, "%s", fr->instance);
			if (fr->title[0])    snprintf(loaded_rule_title[i],    64, "%s", fr->title);
			loaded_rules[i].class    = fr->class[0]    ? loaded_rule_class[i]    : NULL;
			loaded_rules[i].instance = fr->instance[0] ? loaded_rule_instance[i] : NULL;
			loaded_rules[i].title    = fr->title[0]    ? loaded_rule_title[i]    : NULL;
			loaded_rules[i].tags       = fr->tags;
			loaded_rules[i].isfloating = fr->isfloating;
			loaded_rules[i].monitor    = fr->monitor;
		}
		active_rules   = loaded_rules;
		n_active_rules = n;
	}
}

void
configfile_init(const char *path)
{
	configfile_load(path, &g_fileconfig);
	applyconfigfile(&g_fileconfig);
}
