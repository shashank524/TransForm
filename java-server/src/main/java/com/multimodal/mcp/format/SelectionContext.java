package com.multimodal.mcp.format;

/**
 * Input to format selection: data shape, target, optional constraints.
 */
public class SelectionContext {

    private final int nRows;
    private final int nCols;
    private final OptimizationTarget target;
    private final boolean preferStreaming;

    public SelectionContext(int nRows, int nCols) {
        this(nRows, nCols, OptimizationTarget.MIN_LATENCY, false);
    }

    public SelectionContext(int nRows, int nCols, OptimizationTarget target) {
        this(nRows, nCols, target, false);
    }

    public SelectionContext(int nRows, int nCols, OptimizationTarget target, boolean preferStreaming) {
        this.nRows = nRows;
        this.nCols = nCols;
        this.target = target;
        this.preferStreaming = preferStreaming;
    }

    public int getNRows() {
        return nRows;
    }

    public int getNCols() {
        return nCols;
    }

    public OptimizationTarget getTarget() {
        return target;
    }

    public boolean isPreferStreaming() {
        return preferStreaming;
    }
}
