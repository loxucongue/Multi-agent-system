"use client";

import type { SyntheticEvent, ThHTMLAttributes } from "react";
import { useCallback, useMemo, useState } from "react";
import { Resizable } from "react-resizable";
import type { ColumnType, ColumnsType } from "antd/es/table";

type ResizeData = {
  size: {
    width: number;
  };
};

export type ResizableColumnType<T> = ColumnType<T> & {
  resizable?: boolean;
};

export type ResizableColumnsType<T> = ResizableColumnType<T>[];

export function ResizableTitle(
  props: ThHTMLAttributes<HTMLTableCellElement> & {
    onResize?: (event: SyntheticEvent, data: ResizeData) => void;
    width?: number;
  },
) {
  const { onResize, width, ...restProps } = props;

  if (!width || !onResize) {
    return <th {...restProps} />;
  }

  return (
    <Resizable
      width={width}
      height={0}
      minConstraints={[80, 0]}
      handle={
        <span
          className="resizable-handle"
          onClick={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
        />
      }
      onResize={onResize}
      draggableOpts={{ enableUserSelectHack: false }}
    >
      <th {...restProps} />
    </Resizable>
  );
}

export function useResizableColumns<T = unknown>(initialColumns: ResizableColumnsType<T>) {
  const [widths, setWidths] = useState<(number | undefined)[]>(() =>
    initialColumns.map((column) => (typeof column.width === "number" ? column.width : undefined)),
  );

  const handleResize = useCallback(
    (index: number) => (_: SyntheticEvent, { size }: ResizeData) => {
      setWidths((prev) => {
        const next = [...prev];
        next[index] = size.width;
        return next;
      });
    },
    [],
  );

  const mergedColumns = useMemo(
    () =>
      initialColumns.map((column, index) => {
        const width = widths[index];
        const mergedColumn: ResizableColumnType<T> = {
          ...column,
          width,
        };

        if (!width || column.resizable === false) {
          return mergedColumn;
        }

        mergedColumn.onHeaderCell = () =>
          ({
            width,
            onResize: handleResize(index),
          }) as ThHTMLAttributes<HTMLTableCellElement>;

        return mergedColumn;
      }) as ColumnsType<T>,
    [handleResize, initialColumns, widths],
  );

  const components = useMemo(
    () => ({
      header: {
        cell: ResizableTitle,
      },
    }),
    [],
  );

  return [mergedColumns, components] as const;
}
