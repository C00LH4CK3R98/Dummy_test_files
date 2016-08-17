#include <stdio.h>
#include <cv.h>
#include <highgui.h>

int main(){
    CvCapture* webcam = cvCreateCameraCapture(0);
    IplImage*prev=NULL;
    IplImage*next=NULL;

    double pyr_scale=0.5; 
    int levels=1;
    int winsize=3; 
    int iterations=10;
    int poly_n=5; 
    double poly_sigma=1.1;
    int flags=0;

    if (!webcam){
        puts("error!");
        return -1;
    }

    while (1) {
        prev = cvQueryFrame(webcam);
        next = cvQueryFrame(webcam);
        CvSize isize = cvSize(80,80);
        IplImage *flow = cvCreateImage(isize, IPL_DEPTH_32F, 1); 
        if ((prev) && (next)) {
            cvCalcOpticalFlowFarneback(prev,next,flow,pyr_scale,levels,winsize,iterations,poly_n,poly_sigma,flags);
        }
    }

    return 0;
}