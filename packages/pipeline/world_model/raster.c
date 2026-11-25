/* Depth buffer of projected triangles. x, y in buffer pixels, z in camera space; three floats per triangle each. */
#include <math.h>
void raster_depth(const double *x, const double *y, const double *z, long n, float *depth, int w, int h) {
    for (long t = 0; t < n; t++) {
        const double *xs = x + 3 * t, *ys = y + 3 * t, *zs = z + 3 * t;
        double xmin = fmin(xs[0], fmin(xs[1], xs[2])), xmax = fmax(xs[0], fmax(xs[1], xs[2]));
        double ymin = fmin(ys[0], fmin(ys[1], ys[2])), ymax = fmax(ys[0], fmax(ys[1], ys[2]));
        if (xmax <= 0 || xmin >= w || ymax <= 0 || ymin >= h) continue;
        int x0 = (int)floor(xmin), x1 = (int)ceil(xmax) + 1, y0 = (int)floor(ymin), y1 = (int)ceil(ymax) + 1;
        if (x0 < 0) x0 = 0;
        if (y0 < 0) y0 = 0;
        if (x1 > w) x1 = w;
        if (y1 > h) y1 = h;
        double den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2]);
        if (fabs(den) < 1e-9) continue;
        for (int j = y0; j < y1; j++) {
            double py = j + 0.5;
            for (int i = x0; i < x1; i++) {
                double px = i + 0.5;
                double l0 = ((ys[1] - ys[2]) * (px - xs[2]) + (xs[2] - xs[1]) * (py - ys[2])) / den;
                double l1 = ((ys[2] - ys[0]) * (px - xs[2]) + (xs[0] - xs[2]) * (py - ys[2])) / den;
                double l2 = 1 - l0 - l1;
                if (l0 < -1e-4 || l1 < -1e-4 || l2 < -1e-4) continue;
                float zz = (float)(1.0 / (l0 / zs[0] + l1 / zs[1] + l2 / zs[2]));
                if (zz < depth[(long)j * w + i]) depth[(long)j * w + i] = zz;
            }
        }
    }
}
