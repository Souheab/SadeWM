/* configfile.h - Runtime TOML config file loader for sadewm.
 * configfile.c is #included at the bottom of sadewm.c so it can access
 * static symbols. Only this header is needed by callers within sadewm.c.
 */
#ifndef CONFIGFILE_H
#define CONFIGFILE_H

#define CONFIGFILE_MAX_RULES 64
#define CONFIGFILE_MAX_KEYS  256

typedef struct {
	char class[64];
	char instance[64];
	char title[64];
	unsigned int tags;
	int isfloating;
	int monitor;
} FileRule;

typedef struct {
	char mod_strs[8][16];
	int  nmod;
	char key[32];
	char action[32];
	char cmd[256];
	char layout[16];
	int          arg_int;    int has_arg_int;
	unsigned int arg_uint;   int has_arg_uint;
	float        arg_float;  int has_arg_float;
} FileKey;

typedef struct {
	char key[32];
	int  tag;
} FileTagKey;

typedef struct {
	/* appearance */
	unsigned int borderpx;    int has_borderpx;
	unsigned int gappx;       int has_gappx;
	unsigned int snap;        int has_snap;
	char border_norm[8];      int has_border_norm;
	char border_sel[8];       int has_border_sel;
	/* layout */
	float        mfact;           int has_mfact;
	int          nmaster;         int has_nmaster;
	unsigned int topoffset;       int has_topoffset;
	unsigned int bottomoffset;    int has_bottomoffset;
	int          resizehints;     int has_resizehints;
	int          lockfullscreen;  int has_lockfullscreen;
	/* rules */
	int has_rules;
	int nrules;
	FileRule rules[CONFIGFILE_MAX_RULES];
	/* keys */
	int has_keys;
	int nkeys;
	FileKey fkeys[CONFIGFILE_MAX_KEYS];
	/* tagkeys */
	int has_tagkeys;
	int ntagkeys;
	FileTagKey ftagkeys[CONFIGFILE_MAX_KEYS];
} FileConfig;

/* Load the TOML config at `path` and apply it to the running config.
 * If the file is absent or unparseable, compiled-in defaults are kept. */
void configfile_init(const char *path);

/* Print the currently active config (after any overrides) to stdout.
 * Intended for use with the -t dry-run flag. */
void configfile_print(void);

#endif /* CONFIGFILE_H */
