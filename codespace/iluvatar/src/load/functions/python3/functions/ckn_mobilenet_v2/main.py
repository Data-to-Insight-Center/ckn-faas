import torch
from PIL import Image
from torchvision import transforms
from torchvision import models

def pre_process(filename):
    """
    Pre-processes the image to allow the image to be fed into the PyTorch model.
    :param filename: Path to the image file.
    :return: Pre-processed image tensor.
    """
    input_image = Image.open(filename).convert("RGB")  # Ensure the image is in RGB format
    preprocess = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    input_tensor = preprocess(input_image)
    input_batch = input_tensor.unsqueeze(0)
    return input_batch


def predict(input,model):
    """
    Predicting the class for a given pre-processed input
    :param input:
    :return: prediction class
    """
    with torch.no_grad():
        output = model(input)
    prob = torch.nn.functional.softmax(output[0], dim=0)

    # retrieve top probability for the input
    high_prob, pred_label = torch.topk(prob, 1)

    return str((labels[pred_label[0]])), high_prob[0].item()

def load_model(model_name):
    return torch.hub.load('pytorch/vision:v0.10.0', 'model_name', pretrained=True)

def main(args):
    start = time()
    model_name = args.get("model_name",'resnet18')
    filename=''
    preprocessed_input = pre_process(filename)
    model = load_model(model_name)
    prediction, probability = predict(preprocessed_input,model)
    end = time()
    return {"body": {"Using model":model_name, "Probability":probability} }