from pathlib import Path
from typing import List, Dict, Tuple
import json
import argparse
import os


def parse_args():
    parser = argparse.ArgumentParser(description="", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--exp', type=str, help='Experiment name')  

    return parser.parse_args()


def get_center(bbox):
    return [bbox[0] + (bbox[2] - bbox[0]) / 2, bbox[1] + (bbox[3] - bbox[1]) / 2]

def was_static(predictions, occl_ind):
    if occl_ind < 2:
        return True
    static_th = 3.0

    horizon = min(3, occl_ind)

    mean_x = 0
    mean_y = 0
    for i in range(1, horizon + 1):
        center = get_center(predictions[occl_ind - i])
        mean_x += center[0]
        mean_y += center[1]

    mean_center = [mean_x / horizon, mean_y / horizon]
    pre_occl_center = get_center(predictions[occl_ind - 1])
    if abs(mean_center[0] - pre_occl_center[0]) < static_th and abs(mean_center[1] - pre_occl_center[1]) < static_th:
        return True
    else:
        return False

def get_closest(bbox, other_boxes):
    min_dist = 10000
    closest_bbox = None
    snitch_center = get_center(bbox)
    for other_bbox in other_boxes:
        other_center = get_center(other_bbox)
        dist = (snitch_center[0] - other_center[0]) ** 2 + (snitch_center[1] - other_center[1]) ** 2
        if dist < min_dist:
            min_dist = dist
            closest_bbox = other_bbox

    return closest_bbox

def adjust_to_occluder(bbox, prev_bbox, other_boxes, prev_boxes):
    closest_bbox = get_closest(bbox, other_boxes)
    if closest_bbox is None:
        return bbox
    prev_closest_bbox = get_closest(prev_bbox, prev_boxes)

    closest_center = get_center(closest_bbox)

    container_h = closest_bbox[3] - closest_bbox[1]
    adjusted_center = [closest_center[0], closest_center[1] + container_h / 6]
    box_h = bbox[3] - bbox[1]
    box_w = bbox[2] - bbox[0]

    adjusted_box = [adjusted_center[0] - box_w / 2, adjusted_center[1] - box_h / 2, adjusted_center[0] + box_w / 2, adjusted_center[1] + box_h / 2]

    return adjusted_box


def refine(predictions, others, visibility):
    is_visible = False
    was_static_flag = False
    last_visible = None
    move_thresh = 1.0
    post_processed = []
    first_ocluded = None
    first_ocluded_others = None
    for i, bbox in enumerate(predictions):
        if bbox is None:
            post_processed.append(bbox)
            continue

        curr_center = get_center(bbox)
        if visibility[i]:
            is_visible = True
            was_static_flag = False
            post_processed.append(bbox)
            last_visible = bbox
            prev_center = curr_center
            continue

        if is_visible:
            if was_static(predictions, i):
                was_static_flag = True
            first_ocluded = curr_center
            first_ocluded_others = others[i]

        is_moving = abs(first_ocluded[0] - curr_center[0]) > move_thresh or abs(first_ocluded[1] - curr_center[1]) > move_thresh
        
        if was_static_flag and not is_moving:
            post_processed.append(last_visible)
        elif was_static_flag and is_moving:
            post_processed.append(adjust_to_occluder(bbox, post_processed[-1], others[i], first_ocluded_others))
            first_ocluded_others = others[i]
        else:
            post_processed.append(bbox)

        is_visible = False

    return post_processed

if __name__ == '__main__':
    args = parse_args()
    bb_prediction_dir = '../exp/tracking/' + args.exp + '/results/'
    save_dir = '../exp/tracking/' + args.exp + '_pp/results/'
    if not os.path.isdir(save_dir):
        os.mkdir('../exp/tracking/' + args.exp + '_pp')
        os.mkdir(save_dir)
     
    predictions_files = Path(bb_prediction_dir).glob("*_bb.json")
    video_bb_predictions: Dict[str, List[List[int]]] = {}
    video_bb_others: Dict[str, List[List[List[int]]]] = {}
    for f_predict in predictions_files:
        video_name = f_predict.stem[:-3]
        with open(f_predict, "rb") as f:
            snitch_predictions_locations: List[List[int]] = json.load(f)
            video_bb_predictions[video_name] = snitch_predictions_locations
            
        other_boxes_file = bb_prediction_dir + video_name + '_otherbb.json'
        with open(other_boxes_file, "rb") as f:
            other_boxes: List[List[List[int]]] = json.load(f)
            video_bb_others[video_name] = other_boxes

        visibility_file = bb_prediction_dir + video_name + '_visibility.json'
        with open(visibility_file, "rb") as f:
            visibility: List[List[List[int]]] = json.load(f)

        post_processed = refine(snitch_predictions_locations, other_boxes, visibility)

        json.dump(post_processed, open(save_dir + '/%s_bb.json' % video_name, 'w'))