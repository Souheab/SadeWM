package wm

import (
	"github.com/sadewm/sadewm/wm-go/internal/config"
	"github.com/sadewm/sadewm/wm-go/internal/util"
)

// Tag operations

// GetDomTag returns the highest-numbered selected tag.
func (wm *WM) GetDomTag(tags []Tag) *Tag {
	if wm.SelMon.TagSet[wm.SelMon.SelTags] == 0 {
		return nil
	}
	var t *Tag
	for i := range tags {
		if wm.isTagSelected(i) {
			t = &tags[i]
		}
	}
	return t
}

func (wm *WM) getTagIndex(m *Monitor, t *Tag) int {
	if t == nil {
		return -1
	}
	for i := range m.Tags {
		if &m.Tags[i] == t {
			return i
		}
	}
	return -1
}

func (wm *WM) isTagSelected(tagNum int) bool {
	if tagNum >= len(config.Tags) {
		return false
	}
	return (wm.SelMon.TagSet[wm.SelMon.SelTags] & (1 << uint(tagNum))) != 0
}

// ApplyTag copies per-tag state into the monitor.
func (wm *WM) ApplyTag(t *Tag) {
	if t == nil {
		return
	}
	wm.SelMon.NMaster = t.NMaster
	wm.SelMon.MFact = t.MFact
	wm.SelMon.Lt = t.Lt
	wm.SelMon.IsRightTiled = t.IsRightTiled
}

// View switches to the given tag set.
func (wm *WM) View(arg *config.Arg) {
	if (arg.UI & TagMask()) == wm.SelMon.TagSet[wm.SelMon.SelTags] {
		return
	}
	wm.SelMon.SelTags ^= 1
	if arg.UI&TagMask() != 0 {
		wm.SelMon.TagSet[wm.SelMon.SelTags] = arg.UI & TagMask()
		wm.ApplyTag(wm.GetDomTag(wm.SelMon.Tags))
	}
	wm.Focus(wm.NextTiled(wm.SelMon.Clients))
	wm.Arrange(wm.SelMon)
}

// ToggleView toggles tag(s) in the current view.
func (wm *WM) ToggleView(arg *config.Arg) {
	newTagSet := wm.SelMon.TagSet[wm.SelMon.SelTags] ^ (arg.UI & TagMask())
	if newTagSet != 0 {
		wm.SelMon.TagSet[wm.SelMon.SelTags] = newTagSet
		wm.ApplyTag(wm.GetDomTag(wm.SelMon.Tags))
		wm.Focus(nil)
		wm.Arrange(wm.SelMon)
	}
}

// Tag assigns tag(s) to the selected client.
func (wm *WM) Tag(arg *config.Arg) {
	if wm.SelMon.Sel != nil && arg.UI&TagMask() != 0 {
		wm.SelMon.Sel.Tags = arg.UI & TagMask()
		wm.Focus(nil)
		wm.Arrange(wm.SelMon)
	}
}

// ToggleTag toggles tag(s) on the selected client.
func (wm *WM) ToggleTag(arg *config.Arg) {
	if wm.SelMon.Sel == nil {
		return
	}
	newTags := wm.SelMon.Sel.Tags ^ (arg.UI & TagMask())
	if newTags != 0 {
		wm.SelMon.Sel.Tags = newTags
		wm.ApplyTag(wm.GetDomTag(wm.SelMon.Tags))
		wm.Focus(nil)
		wm.Arrange(wm.SelMon)
	}
}

// ViewPrev switches to the previous tag.
func (wm *WM) ViewPrev(arg *config.Arg) {
	t := wm.GetDomTag(wm.SelMon.Tags)
	if t == nil {
		return
	}
	num := t.TagNum
	if num == 0 {
		num = len(config.Tags) - 1
	} else {
		num--
	}
	wm.View(&config.Arg{UI: 1 << uint(num)})
}

// ViewNext switches to the next tag.
func (wm *WM) ViewNext(arg *config.Arg) {
	t := wm.GetDomTag(wm.SelMon.Tags)
	if t == nil {
		return
	}
	num := t.TagNum
	if num == len(config.Tags)-1 {
		num = 0
	} else {
		num++
	}
	wm.View(&config.Arg{UI: 1 << uint(num)})
}

func init() {
	_ = util.LogDebug // ensure import
}
