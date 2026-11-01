"""Historical classic micromouse maze layouts.

All layouts are third-party transcriptions, not official certified originals.
Text files are preserved verbatim in mazes/ for auditing.
Only the *physics* sees the true walls; controllers are sensor-only.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any
import math

MAZE_DIR = Path(__file__).resolve().parent.parent / 'mazes'
SOURCES = {
    'competition_apec_2013': ('2013apec.maze', 'APEC 2013 · Classic 16×16', 'https://www.tcp4me.com/mmr/mazes/2013apec.maze'),
    'competition_apec_2016': ('2016apec.maze', 'APEC 2016 · Classic 16×16', 'https://www.tcp4me.com/mmr/mazes/2016apec.maze'),
    'competition_apec_2018': ('2018apec.maze', 'APEC 2018 · Classic 16×16', 'https://www.tcp4me.com/mmr/mazes/2018apec.maze'),
    'competition_japan_2017': ('2017japan.maze', 'All Japan 2017 · Classic 16×16', 'https://www.tcp4me.com/mmr/mazes/2017japan.maze'),
}

# N=1,E=2,S=4,W=8; bottom-left is cell (0,0).
DIRS = ((0, 1), (1, 0), (0, -1), (-1, 0))


def parse_maze(text: str) -> list[list[int]]:
    """Decode 2-character-per-cell ASCII .maze maps into reciprocal wall masks."""
    rows = text.splitlines()
    if not rows or len(rows) % 2 != 1 or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('Maze must be a rectangular odd-row ASCII grid')
    height = (len(rows) - 1) // 2
    width = (len(rows[0]) - 1) // 2
    if not (2 <= width <= 32 and 2 <= height <= 32):
        raise ValueError('Maze dimensions out of range')
    if len(rows[0]) != 2 * width + 1:
        raise ValueError('Invalid maze row length')
    for i, line in enumerate(rows):
        if i % 2 == 0:
            if any(ch not in '- +' for ch in line):
                if not (i == len(rows) - 1 and line[0] == '.' and all(c in '- +' for c in line[1:])):
                    raise ValueError(f'Invalid horizontal wall row {i}')
        else:
            if any(ch not in '| ' for ch in line):
                raise ValueError(f'Invalid vertical wall row {i}')
    masks = []
    for y in range(height):
        line = 2*(height - 1 - y) + 1
        result = []
        for x in range(width):
            north = rows[line - 1][2*x + 1] == '-'
            east = rows[line][2*x + 2] == '|'
            south = rows[line + 1][2*x + 1] == '-'
            west = rows[line][2*x] == '|'
            result.append(int(north) | (int(east)<<1) | (int(south)<<2) | (int(west)<<3))
        masks.append(result)
    # Historical transcriptions may have absent perimeter walls, but a physical
    # micromouse arena must not let the robot exit the board. Reject rather than
    # silently modify source geometry.
    for y in range(height):
        for x in range(width):
            m=masks[y][x]
            if (x==0 and not m&8) or (x==width-1 and not m&2) or (y==0 and not m&4) or (y==height-1 and not m&1):
                raise ValueError(f'Missing boundary wall at ({x},{y})')
            if x < width-1 and bool(m&2) != bool(masks[y][x+1]&8):
                raise ValueError(f'Inconsistent east/west wall at ({x},{y})')
            if y < height-1 and bool(m&1) != bool(masks[y+1][x]&4):
                raise ValueError(f'Inconsistent north/south wall at ({x},{y})')
    return masks


def reachable(masks: list[list[int]], goals: set[tuple[int,int]]) -> bool:
    w,h=len(masks[0]),len(masks)
    seen={(0,0)}
    q=deque([(0,0)])
    while q:
        x,y=q.popleft()
        if (x,y) in goals:return True
        for d,(dx,dy) in enumerate(DIRS):
            nx,ny=x+dx,y+dy
            if 0 <= nx < w and 0 <= ny < h and not masks[y][x] & (1<<d) and (nx,ny) not in seen:
                seen.add((nx,ny));q.append((nx,ny))
    return False


def wall_rectangles(masks: list[list[int]], cell: float = .18) -> list[tuple[float,float,float,float]]:
    """Merge consecutive collinear walls: faster raycasting than one per cell."""
    w,h=len(masks[0]),len(masks)
    ox=-w*cell/2; oy=-h*cell/2; thickness=.012
    walls=[]
    for gy in range(h+1):
        x=0
        while x<w:
            present = lambda at: bool((masks[gy-1][at]&1) if gy>0 else (masks[0][at]&4))
            if not present(x):x+=1;continue
            start=x
            while x<w and present(x):x+=1
            length=(x-start)*cell+thickness
            walls.append((ox+(start+x)*cell/2,oy+gy*cell,length/2,thickness/2))
    for gx in range(w+1):
        y=0
        while y<h:
            present = lambda at: bool((masks[at][gx-1]&2) if gx>0 else (masks[at][0]&8))
            if not present(y):y+=1;continue
            start=y
            while y<h and present(y):y+=1
            length=(y-start)*cell+thickness
            walls.append((ox+gx*cell,oy+(start+y)*cell/2,thickness/2,length/2))
    return walls


def load_competition_courses() -> dict[str, dict[str, Any]]:
    result={}
    for key,(filename,title,url) in SOURCES.items():
        masks=parse_maze((MAZE_DIR/filename).read_text(encoding='utf-8'))
        w,h=len(masks[0]),len(masks)
        goals={(x,y) for x in (w//2-1,w//2) for y in (h//2-1,h//2)}
        if not reachable(masks,goals):
            raise ValueError(f'{filename} has no traversable route from start to goal')
        cell=.18; ox=-w*cell/2;oy=-h*cell/2
        result[key]={
            'title':title,'start':(ox+.5*cell,oy+.5*cell,math.pi/2),'route':[],
            'walls':wall_rectangles(masks,cell),
            'maze':{'width':w,'height':h,'cell_m':cell,'origin':(ox,oy),'goal_cells':sorted(goals),
                    'source_url':url,'source_note':'Community transcription; confirm against event photos before treating as canonical.'}
        }
    return result
