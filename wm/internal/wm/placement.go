package wm

import "github.com/sadewm/sadewm/wm/internal/config"

func (wm *WM) placeFloatingOnManage(c *Client) {
	if !config.CenterFloating || c == nil || c.Mon == nil {
		return
	}
	if !c.IsFloating || c.IsDock || c.IsFullscreen || c.HasPositionHint {
		return
	}

	frameW := max(c.W, 1)
	frameH := max(c.H+titlebarHeight, 1)

	frameX := c.Mon.WX + (c.Mon.WW-frameW)/2
	frameY := c.Mon.WY + (c.Mon.WH-frameH)/2

	frameX = clampFrameOrigin(frameX, frameW, c.Mon.WX, c.Mon.WW)
	frameY = clampFrameOrigin(frameY, frameH, c.Mon.WY, c.Mon.WH)

	c.X = frameX
	c.Y = frameY + titlebarHeight
}

func clampFrameOrigin(pos, size, areaPos, areaSize int) int {
	if pos+size > areaPos+areaSize {
		pos = areaPos + areaSize - size
	}
	return max(pos, areaPos)
}
