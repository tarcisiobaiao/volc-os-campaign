#import <Foundation/Foundation.h>
#import <Vision/Vision.h>

// Local image bytes on stdin. No path, image or OCR output is logged.
int main(void) {
    @autoreleasepool {
        NSData *data = [[NSFileHandle fileHandleWithStandardInput] readDataToEndOfFile];
        if (data.length == 0) return 1;
        VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] init];
        request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
        request.usesLanguageCorrection = NO;
        request.recognitionLanguages = @[@"pt-BR", @"en-US", @"es-ES"];
        VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithData:data options:@{}];
        NSError *error = nil;
        if (![handler performRequests:@[request] error:&error]) return 2;
        NSMutableArray<NSString *> *texts = [NSMutableArray array];
        for (VNRecognizedTextObservation *observation in request.results) {
            VNRecognizedText *text = [[observation topCandidates:1] firstObject];
            if (text.string) [texts addObject:text.string];
        }
        NSData *json = [NSJSONSerialization dataWithJSONObject:@{
            @"text": [texts componentsJoinedByString:@"\n"], @"completed": @YES
        } options:0 error:&error];
        if (!json) return 3;
        [[NSFileHandle fileHandleWithStandardOutput] writeData:json];
        return 0;
    }
}
