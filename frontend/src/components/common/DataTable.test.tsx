import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DataTable, DataTableBody, DataTableCell, DataTableContainer, DataTableHead, DataTableHeader, DataTableRow } from './DataTable'

function renderTable(selected = false) {
  return render(
    <DataTableContainer>
      <DataTable>
        <DataTableHeader>
          <tr>
            <DataTableHead>Title</DataTableHead>
          </tr>
        </DataTableHeader>
        <DataTableBody>
          <DataTableRow selected={selected} tabIndex={0} data-testid="row">
            <DataTableCell>Row</DataTableCell>
          </DataTableRow>
        </DataTableBody>
      </DataTable>
    </DataTableContainer>
  )
}
const classes = (el: Element) => el.className.split(/\s+/)

describe('DataTable', () => {
  it('header and rows are 48px', () => {
    renderTable()
    expect(classes(screen.getByRole('columnheader'))).toContain('h-12')
    expect(classes(screen.getByTestId('row'))).toContain('h-12')
    expect(classes(screen.getByRole('cell'))).toContain('h-12')
  })

  it('default and hover states: surface, recessed surface on hover', () => {
    renderTable()
    const row = screen.getByTestId('row')
    expect(classes(row)).toEqual(expect.arrayContaining(['bg-card', 'hover:bg-muted']))
    expect(row).not.toHaveAttribute('data-selected')
    expect(row).not.toHaveAttribute('aria-selected')
  })

  it('selected state: accent + 2px primary bar, independent of hover', () => {
    renderTable(true)
    const row = screen.getByTestId('row')
    expect(row).toHaveAttribute('data-selected', 'true')
    expect(row).toHaveAttribute('aria-selected', 'true')
    const cls = classes(row)
    expect(cls).toContain('data-[selected=true]:bg-accent')
    // hover never replaces the selected background
    expect(cls).toContain('data-[selected=true]:hover:bg-accent')
    // the bar is keyed on the selected state only, not on :hover
    const bar = cls.find((c) => c.includes('inset_2px_0_0_var(--primary)'))
    expect(bar).toBeDefined()
    expect(bar).toMatch(/^data-\[selected=true\]:/)
    expect(bar).not.toContain('hover')
  })

  it('focus state: 2px outline with 2px offset, keyboard-visible, also when selected', () => {
    renderTable(true)
    const cls = classes(screen.getByTestId('row'))
    expect(cls).toEqual(expect.arrayContaining(['focus-visible:outline-2', 'focus-visible:outline-offset-2', 'focus-visible:outline-ring']))
  })

  it('state container keeps a 240px minimum height without adding a scroll area', () => {
    const { container } = renderTable()
    const box = container.querySelector('[data-slot="data-table-container"]') as HTMLElement
    expect(classes(box)).toContain('min-h-[240px]')
    expect(box.className).not.toMatch(/overflow/)
  })
})
