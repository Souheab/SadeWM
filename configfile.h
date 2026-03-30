/* configfile.h - Runtime TOML config file loader for sadewm.
 * configfile.c is #included at the bottom of sadewm.c so it can access
 * static symbols. Only this header is needed by callers within sadewm.c.
 */
#ifndef CONFIGFILE_H
#define CONFIGFILE_H

#define CONFIGFILE_MAX_RULES 64

typedef struct {
	char class[64];
	char instance[64];
	char title[64];
	unsigned int tags;
	int isfloating;
	int monitor;
} FileRule;

typedef struct {
	/* appearance */
	unsigned int borderpx;  int has_borderpx;
	unsigned int gappx;     int has_gappx;
	unsigned int snap;      int has_snap;
	char font[128];         int has_font;
	/* colors[scheme][slot]: 0=fg, 1=bg, 2=border */
	char colors[2][3][8];
	int  has_colors[2][3];
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
} FileConfig;

/* Load the TOML config at `path` and apply it to the running config.
 * If the file is absent or unparseable, compiled-in defaults are kept. */
void configfile_init(const char *path);

#endif /* CONFIGFILE_H */
