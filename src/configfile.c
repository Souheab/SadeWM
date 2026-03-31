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

/* Persistent storage for merged keybindings. */
static Key  loaded_keys[CONFIGFILE_MAX_KEYS];
static char loaded_key_cmds[CONFIGFILE_MAX_KEYS][256];
static const char *loaded_key_shcmd[CONFIGFILE_MAX_KEYS][4];

/* ---- modifier name → mask lookup ---- */
static const struct { const char *name; unsigned int mask; } mod_table[] = {
	{ "super",   Mod4Mask    },
	{ "alt",     Mod1Mask    },
	{ "shift",   ShiftMask   },
	{ "control", ControlMask },
	{ "ctrl",    ControlMask },
	{ NULL, 0 }
};

static unsigned int
resolve_mods(const FileKey *fk)
{
	unsigned int mask = 0;
	int i, j;
	for (i = 0; i < fk->nmod; i++)
		for (j = 0; mod_table[j].name; j++)
			if (strcasecmp(fk->mod_strs[i], mod_table[j].name) == 0) {
				mask |= mod_table[j].mask;
				break;
			}
	return mask;
}

/* ---- action name → function pointer lookup ---- */
static const struct { const char *name; void (*func)(const Arg *); } func_table[] = {
	{ "spawn",          spawn          },
	{ "focusstack",     focusstack     },
	{ "focusup",        focusup        },
	{ "focusdown",      focusdown      },
	{ "focusleft",      focusleft      },
	{ "focusright",     focusright     },
	{ "focusmon",       focusmon       },
	{ "swapup",         swapup         },
	{ "swapdown",       swapdown       },
	{ "swapleft",       swapleft       },
	{ "swapright",      swapright      },
	{ "zoom",           zoom           },
	{ "killclient",     killclient     },
	{ "minimize",       minimize       },
	{ "restore",        restore        },
	{ "view",           view           },
	{ "reloadconfig",   reloadconfig   },
	{ "viewprev",       viewprev       },
	{ "viewnext",       viewnext       },
	{ "toggleview",     toggleview     },
	{ "tag",            tag            },
	{ "toggletag",      toggletag      },
	{ "tagmon",         tagmon         },
	{ "setlayout",      setlayout      },
	{ "setmfact",       setmfact       },
	{ "setgaps",        setgaps        },
	{ "incnmaster",     incnmaster     },
	{ "togglefloating", togglefloating },
	{ "togglefullscr",  togglefullscr  },
	{ "togglemaximize", togglemaximize },
	{ "toggletiledir",  toggletiledir  },
	{ "layoutnext",     layoutnext     },
	{ "layoutprev",     layoutprev     },
	{ "movemouse",      movemouse      },
	{ "resizemouse",    resizemouse    },
	{ "quit",           quit           },
	{ "togglebar",      togglebar      },
	{ NULL, NULL }
};

static void (*resolve_func(const char *name))(const Arg *)
{
	int i;
	for (i = 0; func_table[i].name; i++)
		if (strcmp(name, func_table[i].name) == 0)
			return func_table[i].func;
	return NULL;
}

static const char *
resolve_funcname(void (*func)(const Arg *))
{
	int i;
	for (i = 0; func_table[i].name; i++)
		if (func_table[i].func == func)
			return func_table[i].name;
	return "?";
}

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

	/* [colors.norm] / [colors.sel] — border only */
	v = toml_seek(root, "colors.norm.border");
	if (v.type == TOML_STRING) {
		snprintf(out->border_norm, sizeof out->border_norm, "%s", v.u.s);
		out->has_border_norm = 1;
	}
	v = toml_seek(root, "colors.sel.border");
	if (v.type == TOML_STRING) {
		snprintf(out->border_sel, sizeof out->border_sel, "%s", v.u.s);
		out->has_border_sel = 1;
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

	/* [[keys]] */
	{
		toml_datum_t keys_arr = toml_get(root, "keys");
		if (keys_arr.type == TOML_ARRAY) {
			int n = keys_arr.u.arr.size;
			int i;
			if (n > CONFIGFILE_MAX_KEYS) n = CONFIGFILE_MAX_KEYS;
			out->has_keys = 1;
			out->nkeys    = n;
			for (i = 0; i < n; i++) {
				toml_datum_t entry = keys_arr.u.arr.elem[i];
				FileKey *fk = &out->fkeys[i];
				if (entry.type != TOML_TABLE) continue;

				/* mod = ["super", "shift"] */
				v = toml_get(entry, "mod");
				if (v.type == TOML_ARRAY) {
					int nm = v.u.arr.size;
					int j;
					if (nm > 8) nm = 8;
					fk->nmod = nm;
					for (j = 0; j < nm; j++) {
						toml_datum_t ms = v.u.arr.elem[j];
						if (ms.type == TOML_STRING)
							snprintf(fk->mod_strs[j], sizeof fk->mod_strs[j], "%s", ms.u.s);
					}
				}

				v = toml_get(entry, "key");
				if (v.type == TOML_STRING)
					snprintf(fk->key, sizeof fk->key, "%s", v.u.s);

				v = toml_get(entry, "action");
				if (v.type == TOML_STRING)
					snprintf(fk->action, sizeof fk->action, "%s", v.u.s);

				v = toml_get(entry, "cmd");
				if (v.type == TOML_STRING)
					snprintf(fk->cmd, sizeof fk->cmd, "%s", v.u.s);

				v = toml_get(entry, "layout");
				if (v.type == TOML_STRING)
					snprintf(fk->layout, sizeof fk->layout, "%s", v.u.s);

				v = toml_get(entry, "arg_int");
				if (v.type == TOML_INT64) { fk->arg_int = (int)v.u.int64; fk->has_arg_int = 1; }

				v = toml_get(entry, "arg_uint");
				if (v.type == TOML_INT64) { fk->arg_uint = (unsigned int)v.u.int64; fk->has_arg_uint = 1; }

				v = toml_get(entry, "arg_float");
				if      (v.type == TOML_FP64)  { fk->arg_float = (float)v.u.fp64;  fk->has_arg_float = 1; }
				else if (v.type == TOML_INT64)  { fk->arg_float = (float)v.u.int64; fk->has_arg_float = 1; }
			}
		}
	}

	/* [[tagkeys]] */
	{
		toml_datum_t tk_arr = toml_get(root, "tagkeys");
		if (tk_arr.type == TOML_ARRAY) {
			int n = tk_arr.u.arr.size;
			int i;
			if (n > CONFIGFILE_MAX_KEYS) n = CONFIGFILE_MAX_KEYS;
			out->has_tagkeys = 1;
			out->ntagkeys    = n;
			for (i = 0; i < n; i++) {
				toml_datum_t entry = tk_arr.u.arr.elem[i];
				FileTagKey *tk = &out->ftagkeys[i];
				if (entry.type != TOML_TABLE) continue;

				v = toml_get(entry, "key");
				if (v.type == TOML_STRING)
					snprintf(tk->key, sizeof tk->key, "%s", v.u.s);

				v = toml_get(entry, "tag");
				if (v.type == TOML_INT64)
					tk->tag = (int)v.u.int64;
			}
		}
	}

	toml_free(res);
}

static void
applyconfigfile(const FileConfig *fc)
{
	if (fc->has_borderpx)      borderpx      = fc->borderpx;
	if (fc->has_gappx)         gappx         = fc->gappx;
	if (fc->has_snap)          snap          = fc->snap;
	if (fc->has_border_norm)   snprintf(col_border_norm, sizeof col_border_norm, "%s", fc->border_norm);
	if (fc->has_border_sel)    snprintf(col_border_sel,  sizeof col_border_sel,  "%s", fc->border_sel);

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

	/* merge keybindings */
	if (fc->has_keys || fc->has_tagkeys) {
		int count, i, j;
		/* start from compiled-in keys */
		count = LENGTH(keys);
		if (count > CONFIGFILE_MAX_KEYS) count = CONFIGFILE_MAX_KEYS;
		for (i = 0; i < count; i++)
			loaded_keys[i] = keys[i];

		/* merge [[keys]] */
		if (fc->has_keys) {
			for (i = 0; i < fc->nkeys; i++) {
				const FileKey *fk = &fc->fkeys[i];
				unsigned int mod = resolve_mods(fk);
				KeySym ks = XStringToKeysym(fk->key);
				if (ks == NoSymbol) {
					fprintf(stderr, "sadewm: unknown keysym \"%s\", skipping\n", fk->key);
					continue;
				}

				/* action = "none" → unbind */
				if (strcmp(fk->action, "none") == 0) {
					for (j = 0; j < count; j++) {
						if (loaded_keys[j].keysym == ks && loaded_keys[j].mod == mod) {
							memmove(&loaded_keys[j], &loaded_keys[j+1],
								(count - j - 1) * sizeof(Key));
							count--;
							break;
						}
					}
					continue;
				}

				void (*func)(const Arg *) = resolve_func(fk->action);
				if (!func) {
					fprintf(stderr, "sadewm: unknown action \"%s\", skipping\n", fk->action);
					continue;
				}

				/* build arg */
				Arg arg = {0};
				if (fk->cmd[0]) {
					/* find a slot index for persistent storage */
					int slot = -1;
					for (j = 0; j < count; j++) {
						if (loaded_keys[j].keysym == ks && loaded_keys[j].mod == mod) {
							slot = j; break;
						}
					}
					if (slot < 0) {
						if (count >= CONFIGFILE_MAX_KEYS) continue;
						slot = count;
					}
					snprintf(loaded_key_cmds[slot], sizeof loaded_key_cmds[slot],
						"%s", fk->cmd);
					loaded_key_shcmd[slot][0] = "/bin/sh";
					loaded_key_shcmd[slot][1] = "-c";
					loaded_key_shcmd[slot][2] = loaded_key_cmds[slot];
					loaded_key_shcmd[slot][3] = NULL;
					arg.v = loaded_key_shcmd[slot];
				} else if (fk->layout[0]) {
					if (strcmp(fk->layout, "tile") == 0)
						arg.v = &layouts[TILE];
					else if (strcmp(fk->layout, "float") == 0)
						arg.v = &layouts[FLOAT];
				} else if (fk->has_arg_float) {
					arg.f = fk->arg_float;
				} else if (fk->has_arg_uint) {
					arg.ui = fk->arg_uint;
				} else if (fk->has_arg_int) {
					arg.i = fk->arg_int;
				}

				/* find existing (mod, keysym) to overwrite, or append */
				int found = 0;
				for (j = 0; j < count; j++) {
					if (loaded_keys[j].keysym == ks && loaded_keys[j].mod == mod) {
						loaded_keys[j].func = func;
						loaded_keys[j].arg  = arg;
						found = 1;
						break;
					}
				}
				if (!found && count < CONFIGFILE_MAX_KEYS) {
					loaded_keys[count].mod    = mod;
					loaded_keys[count].keysym = ks;
					loaded_keys[count].func   = func;
					loaded_keys[count].arg    = arg;
					count++;
				}
			}
		}

		/* merge [[tagkeys]] */
		if (fc->has_tagkeys) {
			for (i = 0; i < fc->ntagkeys; i++) {
				const FileTagKey *tk = &fc->ftagkeys[i];
				KeySym ks = XStringToKeysym(tk->key);
				if (ks == NoSymbol) {
					fprintf(stderr, "sadewm: unknown tagkey keysym \"%s\", skipping\n", tk->key);
					continue;
				}
				if (tk->tag < 0 || tk->tag > 8) continue;

				struct { unsigned int mod; void (*func)(const Arg *); } tkmaps[4] = {
					{ MODKEY,                         view       },
					{ MODKEY|ControlMask,             toggleview },
					{ MODKEY|ShiftMask,               tag        },
					{ MODKEY|ControlMask|ShiftMask,   toggletag  },
				};

				int m;
				for (m = 0; m < 4; m++) {
					unsigned int mod = tkmaps[m].mod;
					Arg arg = { .ui = 1u << tk->tag };
					int found = 0;
					for (j = 0; j < count; j++) {
						if (loaded_keys[j].keysym == ks && loaded_keys[j].mod == mod) {
							loaded_keys[j].func = tkmaps[m].func;
							loaded_keys[j].arg  = arg;
							found = 1;
							break;
						}
					}
					if (!found && count < CONFIGFILE_MAX_KEYS) {
						loaded_keys[count].mod    = mod;
						loaded_keys[count].keysym = ks;
						loaded_keys[count].func   = tkmaps[m].func;
						loaded_keys[count].arg    = arg;
						count++;
					}
				}
			}
		}

		active_keys   = loaded_keys;
		n_active_keys = count;
	}
}

void
configfile_init(const char *path)
{
	configfile_load(path, &g_fileconfig);
	applyconfigfile(&g_fileconfig);
}

void
configfile_print(void)
{
	int i;

	printf("[appearance]\n");
	printf("  borderpx      = %u\n", borderpx);
	printf("  gappx         = %u\n", gappx);
	printf("  snap          = %u\n", snap);

	printf("[colors.norm]\n");
	printf("  border        = \"%s\"\n", col_border_norm);
	printf("[colors.sel]\n");
	printf("  border        = \"%s\"\n", col_border_sel);

	printf("[layout]\n");
	printf("  mfact         = %.2f\n", mfact);
	printf("  nmaster       = %d\n",  nmaster);
	printf("  topoffset     = %u\n",  topoffset);
	printf("  bottomoffset  = %u\n",  bottomoffset);
	printf("  resizehints   = %d\n",  resizehints);
	printf("  lockfullscreen= %d\n",  lockfullscreen);

	printf("[[rules]]  (%d active)\n", n_active_rules);
	for (i = 0; i < n_active_rules; i++) {
		const Rule *r = &active_rules[i];
		printf("  [%d] class=%-16s instance=%-16s title=%-16s "
		       "tags=0x%x isfloating=%d monitor=%d\n",
		       i,
		       r->class    ? r->class    : "(any)",
		       r->instance ? r->instance : "(any)",
		       r->title    ? r->title    : "(any)",
		       r->tags, r->isfloating, r->monitor);
	}

	printf("[[keys]]  (%d active)\n", n_active_keys);
	for (i = 0; i < n_active_keys; i++) {
		const Key *k = &active_keys[i];
		const char *ksname = XKeysymToString(k->keysym);
		const char *fname  = resolve_funcname(k->func);
		char modbuf[64] = "";
		if (k->mod & Mod4Mask)    strcat(modbuf, "super+");
		if (k->mod & Mod1Mask)    strcat(modbuf, "alt+");
		if (k->mod & ControlMask) strcat(modbuf, "ctrl+");
		if (k->mod & ShiftMask)   strcat(modbuf, "shift+");
		/* remove trailing '+' */
		{
			size_t len = strlen(modbuf);
			if (len > 0 && modbuf[len-1] == '+') modbuf[len-1] = '\0';
		}
		printf("  [%d] %-24s %-8s -> %-18s",
		       i, modbuf, ksname ? ksname : "?", fname);
		if (strcmp(fname, "spawn") == 0 && k->arg.v) {
			const char **argv = (const char **)k->arg.v;
			/* SHCMD: argv = {"/bin/sh", "-c", cmd, NULL} */
			if (argv[0] && argv[1] && strcmp(argv[1], "-c") == 0 && argv[2])
				printf(" cmd=\"%s\"", argv[2]);
			else if (argv[0])
				printf(" cmd=\"%s\"", argv[0]);
		} else if (strcmp(fname, "setlayout") == 0 && k->arg.v) {
			const Layout *lt = (const Layout *)k->arg.v;
			printf(" layout=\"%s\"", lt->symbol);
		} else if (strcmp(fname, "setmfact") == 0) {
			printf(" f=%.2f", k->arg.f);
		} else if (k->arg.ui != 0) {
			printf(" ui=0x%x", k->arg.ui);
		} else if (k->arg.i != 0) {
			printf(" i=%d", k->arg.i);
		}
		printf("\n");
	}
}
