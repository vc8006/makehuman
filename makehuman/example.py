# file1 = open("default_data.txt","w")
# data = ["0.1\n","0.1\n","0.1\n","0.1\n","0.1\n","0.1\n","0.1\n","0.1\n"]
# file1.writelines(data)

# file1.close()

class myData:
    def __init__(self,vals):
        self.data = {
            "age" : vals["age"],
            "gender" : vals["gender"],
            "weight" : vals["weight"],
            "muscle" : vals["muscle"],
            "height" : vals["height"],
            "breastSize" : vals["breastSize"],
            "breastFirmness" : vals["breastFirmness"],
            "bodyProportions" : vals["bodyProportions"]
        }

d = {
    "age" : 0.1,
    "gender" : 0.1,
    "weight" : 0.1,
    "muscle" : 0.4,
    "height" : 0.5,
    "breastSize" : 0.4,
    "breastFirmness" : 0.5,
    "bodyProportions" : 0.5
}
o = myData(d)
data = o.data
print(data)