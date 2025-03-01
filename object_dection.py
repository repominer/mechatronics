from ultralytics import YOLO

model = YOLO('yolov8s.pt')

class ObjectDetection:
    def __init__(self):
        pass

    def inference(self, img):
        results = model(img, verbose=False, conf=0.5)

        boxes = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                label = result.names[int(box.cls[0])]
                conf = float(box.conf[0])

                boxes.append({
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "label": label,
                    "conf": conf
                })

        return boxes
