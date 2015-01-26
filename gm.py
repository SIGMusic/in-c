# The existence of these three separate data structures
# is obviously an ugly hack. I blame GtkComboBox.
gm_names = {}
gm_numbers = {}
gm_name_list = []

for line in open('gm_table'):
    if len(line) == 0 or line[0] == '#':
        continue
    num, name = line.split(' ', 1)
    num = int(num) - 1 # File is 1 to 128, we want 0 to 127
    gm_names[num] = name
    gm_numbers[name] = num
    gm_name_list.append(name)
    
def is_valid(num):
    return num in gm_names

def general_midi_name(num):
    try:
        return gm_names[num]
    except:
        return 'Unknown'
